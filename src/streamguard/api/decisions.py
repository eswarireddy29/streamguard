"""
src/streamguard/api/decisions.py

Task 21 - the decision layer, separate from the model.

WHY THIS IS NOT JUST A THRESHOLD. A score answers "how likely is this
fraud?". A decision answers "what do we do?", and that question has
inputs the model does not have:

  - a card reported stolen must be blocked at ANY score. The model
    has never seen that card's theft report; it only sees behaviour.
  - a regulator may require every transaction above a value to be
    reviewed regardless of risk.
  - a merchant under investigation may need every transaction held.
  - analyst capacity is finite: 100 reviews a day means the queue
    cannot be allowed to grow without bound.

Putting these in the model would be wrong - they are policy, they
change weekly, and they must be auditable one rule at a time. Putting
them in the scorer would mix a measurement with a business decision.

EVERY DECISION RECORDS WHY. A fraud analyst asked "why was this
blocked?" must get an answer that names the rule or the score, not a
shrug. That is also what Task 22's audit trail needs.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum


class Decision(str, Enum):
    APPROVE = "approve"
    REVIEW = "review"
    BLOCK = "block"


# Order matters: a rule that blocks outranks one that reviews.
SEVERITY = {Decision.APPROVE: 0, Decision.REVIEW: 1, Decision.BLOCK: 2}


@dataclass
class RuleHit:
    """One rule that fired, and what it wanted."""
    rule: str
    decision: Decision
    reason: str

    def to_dict(self) -> dict:
        return {"rule": self.rule, "decision": self.decision.value,
                "reason": self.reason}


@dataclass
class DecisionResult:
    """The final decision and the full reasoning behind it."""
    decision: Decision
    source: str                  # "rule" or "model"
    probability: float
    threshold_block: float
    threshold_review: float
    model_decision: Decision     # what the score alone would have said
    rules_fired: list = field(default_factory=list)
    overridden: bool = False     # did a rule change the model's answer?

    def to_dict(self) -> dict:
        d = asdict(self)
        d["decision"] = self.decision.value
        d["model_decision"] = self.model_decision.value
        d["rules_fired"] = [r.to_dict() for r in self.rules_fired]
        return d

    def explain(self) -> str:
        """One sentence an analyst can read."""
        if self.rules_fired:
            top = self.rules_fired[0]
            if self.overridden:
                return (f"{self.decision.value.upper()} by rule "
                        f"'{top.rule}' ({top.reason}), overriding the "
                        f"model's {self.model_decision.value} "
                        f"at p={self.probability:.4f}")
            return (f"{self.decision.value.upper()} - rule '{top.rule}' "
                    f"({top.reason}) and the model agree "
                    f"at p={self.probability:.4f}")
        return (f"{self.decision.value.upper()} on the model score "
                f"p={self.probability:.4f} (block >= "
                f"{self.threshold_block:.5f})")


# ---------------------------------------------------------------------
#  Policy state: things the model cannot know
# ---------------------------------------------------------------------

@dataclass
class PolicyLists:
    """Facts from outside the transaction stream.

    In production these come from a fraud operations system and change
    continuously. Here they are in-memory sets with an API to update
    them, which is enough to demonstrate the mechanism and to test it.
    """
    blocked_cards: set = field(default_factory=set)
    blocked_merchants: set = field(default_factory=set)
    blocked_devices: set = field(default_factory=set)
    trusted_cards: set = field(default_factory=set)
    watched_merchants: set = field(default_factory=set)

    def summary(self) -> dict:
        return {
            "blocked_cards": len(self.blocked_cards),
            "blocked_merchants": len(self.blocked_merchants),
            "blocked_devices": len(self.blocked_devices),
            "trusted_cards": len(self.trusted_cards),
            "watched_merchants": len(self.watched_merchants),
        }


@dataclass
class DecisionConfig:
    """Thresholds and rule parameters.

    Thresholds come from Task 16's cost optimisation, not from 0.5:
    missing fraud costs Rs 5,000, blocking a customer Rs 200, a 25:1
    asymmetry that puts the optimum at 0.03061.
    """
    threshold_block: float = 0.03061
    threshold_review: float = 0.01113

    # Mandatory review above this amount, whatever the score. A real
    # bank has reporting obligations on large transactions; a low
    # fraud score does not remove them.
    high_value_review: float = 200_000.0

    # Hard block above this, whatever the score. The downside of
    # wrongly blocking one very large transaction is smaller than the
    # downside of approving a fraudulent one.
    very_high_value_block: float = 1_000_000.0

    # A trusted card still gets reviewed above this, so "trusted"
    # cannot be used as an unlimited bypass.
    trusted_review_above: float = 100_000.0


class DecisionEngine:
    """Turns a score into a decision, applying policy rules first.

    RULE ORDER AND PRECEDENCE: all rules are evaluated, not just the
    first match, because the audit trail should record everything that
    applied. The most severe outcome wins. A rule can only make the
    decision MORE severe than the model's, never less - except the
    explicit trusted-card rule, which is bounded by an amount.
    """

    def __init__(self, config: DecisionConfig | None = None,
                 lists: PolicyLists | None = None):
        self.cfg = config or DecisionConfig()
        self.lists = lists or PolicyLists()
        self.counts = {d.value: 0 for d in Decision}
        self.rule_counts: dict = {}
        self.overrides = 0

    # ---------- the rules ----------

    def _rules(self, payload: dict, prob: float) -> list:
        """Every rule that fires for this transaction."""
        hits = []
        card = str(payload.get("card_ref", ""))
        merchant = str(payload.get("merchant_ref", ""))
        device = payload.get("device_ref")
        amount = float(payload.get("amount", 0.0))

        # --- hard blocks: facts the model cannot know ---
        if card in self.lists.blocked_cards:
            hits.append(RuleHit(
                "card_blocked", Decision.BLOCK,
                "card is on the blocked list (reported stolen or compromised)"))

        if merchant in self.lists.blocked_merchants:
            hits.append(RuleHit(
                "merchant_blocked", Decision.BLOCK,
                "merchant is on the blocked list"))

        if device and str(device) in self.lists.blocked_devices:
            hits.append(RuleHit(
                "device_blocked", Decision.BLOCK,
                "device is on the blocked list"))

        # --- value thresholds ---
        if amount >= self.cfg.very_high_value_block:
            hits.append(RuleHit(
                "very_high_value", Decision.BLOCK,
                f"amount {amount:,.0f} is at or above the hard block "
                f"limit {self.cfg.very_high_value_block:,.0f}"))
        elif amount >= self.cfg.high_value_review:
            hits.append(RuleHit(
                "high_value", Decision.REVIEW,
                f"amount {amount:,.0f} requires review above "
                f"{self.cfg.high_value_review:,.0f}"))

        # --- watched merchants ---
        if merchant in self.lists.watched_merchants:
            hits.append(RuleHit(
                "merchant_watched", Decision.REVIEW,
                "merchant is under investigation"))

        # --- trusted cards: the only rule that can REDUCE severity ---
        if (card in self.lists.trusted_cards
                and amount < self.cfg.trusted_review_above
                and card not in self.lists.blocked_cards):
            hits.append(RuleHit(
                "card_trusted", Decision.APPROVE,
                f"card is trusted and amount {amount:,.0f} is below "
                f"{self.cfg.trusted_review_above:,.0f}"))

        # Most severe first, so explain() names the decisive rule.
        hits.sort(key=lambda h: -SEVERITY[h.decision])
        return hits

    def _from_score(self, prob: float) -> Decision:
        if prob >= self.cfg.threshold_block:
            return Decision.BLOCK
        if prob >= self.cfg.threshold_review:
            return Decision.REVIEW
        return Decision.APPROVE

    # ---------- the decision ----------

    def decide(self, payload: dict, probability: float) -> DecisionResult:
        """Apply the rules, then the score. Most severe wins."""
        model_decision = self._from_score(probability)
        hits = self._rules(payload, probability)

        final = model_decision
        source = "model"

        blocking = [h for h in hits if h.decision != Decision.APPROVE]
        if blocking:
            strongest = max(blocking, key=lambda h: SEVERITY[h.decision])
            if SEVERITY[strongest.decision] > SEVERITY[final]:
                final = strongest.decision
                source = "rule"

        # A trusted card can lower a REVIEW to APPROVE, but never a
        # BLOCK. Trust is not a licence to skip a strong fraud signal.
        trusted = [h for h in hits if h.rule == "card_trusted"]
        if (trusted and not blocking and final == Decision.REVIEW):
            final = Decision.APPROVE
            source = "rule"

        overridden = final != model_decision

        self.counts[final.value] += 1
        if overridden:
            self.overrides += 1
        for h in hits:
            self.rule_counts[h.rule] = self.rule_counts.get(h.rule, 0) + 1

        return DecisionResult(
            decision=final,
            source=source,
            probability=probability,
            threshold_block=self.cfg.threshold_block,
            threshold_review=self.cfg.threshold_review,
            model_decision=model_decision,
            rules_fired=hits,
            overridden=overridden,
        )

    # ---------- operations ----------

    def block_card(self, card_ref: str, reason: str = "") -> None:
        self.lists.blocked_cards.add(str(card_ref))

    def trust_card(self, card_ref: str) -> None:
        self.lists.trusted_cards.add(str(card_ref))

    def watch_merchant(self, merchant_ref: str) -> None:
        self.lists.watched_merchants.add(str(merchant_ref))

    def stats(self) -> dict:
        total = sum(self.counts.values())
        return {
            "decisions": dict(self.counts),
            "total": total,
            "overrides": self.overrides,
            "override_rate": self.overrides / total if total else 0.0,
            "rules_fired": dict(self.rule_counts),
            "lists": self.lists.summary(),
            "thresholds": {
                "block": self.cfg.threshold_block,
                "review": self.cfg.threshold_review,
            },
        }