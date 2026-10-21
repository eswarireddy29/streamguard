"""
tests/test_decisions.py

Task 28 - the decision engine, as PASS/FAIL.

Task 21 verified these with a script that printed a table a human had
to read. That works once. It stops working when someone adds a rule
three weeks later and does not remember what the table said.

These are pure functions with no database and no server, so the whole
file runs in milliseconds and can run on every change.
"""

from __future__ import annotations

import pytest

from streamguard.api.decisions import (
    Decision, DecisionConfig, DecisionEngine, PolicyLists, SEVERITY,
)


def payload(card="CARD0000001", merchant="MERCH000001",
            device="DEV0000001", amount=1000.0) -> dict:
    """Every field has a default, so each test overrides only what it
    is about. Same pattern as the Task 11 make_payload fixture."""
    return {"card_ref": card, "merchant_ref": merchant,
            "device_ref": device, "amount": amount}


@pytest.fixture
def engine():
    """A fresh engine per test.

    Shared state makes results depend on execution order, which
    produces failures that appear and vanish at random - the test
    pollution problem recorded at Task 11.
    """
    e = DecisionEngine(DecisionConfig())
    e.block_card("CARD_STOLEN")
    e.trust_card("CARD_TRUSTED")
    e.watch_merchant("MERCH_WATCHED")
    return e


class TestScoreThresholds:
    """With no rule firing, the score alone decides."""

    def test_low_score_approves(self, engine):
        r = engine.decide(payload(), 0.001)
        assert r.decision == Decision.APPROVE
        assert r.source == "model"
        assert not r.overridden

    def test_review_band(self, engine):
        r = engine.decide(payload(), 0.02)
        assert r.decision == Decision.REVIEW

    def test_block_band(self, engine):
        r = engine.decide(payload(), 0.50)
        assert r.decision == Decision.BLOCK

    def test_thresholds_come_from_task_16(self, engine):
        """Not 0.5. The cost asymmetry is 25:1, so the optimum is
        far below the default."""
        assert engine.cfg.threshold_block == pytest.approx(0.03061)
        assert engine.cfg.threshold_review == pytest.approx(0.01113)

    def test_boundary_is_inclusive(self, engine):
        """A score exactly at the threshold blocks. An off-by-one here
        would silently approve the marginal cases."""
        r = engine.decide(payload(), engine.cfg.threshold_block)
        assert r.decision == Decision.BLOCK


class TestPolicyOverrides:
    """Facts the model cannot know must win."""

    def test_stolen_card_blocks_at_near_zero_score(self, engine):
        """THE DECISIVE TEST. The model has never seen the theft
        report - it only sees behaviour. A card reported stolen this
        morning must block even at p=0.0001."""
        r = engine.decide(payload(card="CARD_STOLEN"), 0.0001)
        assert r.decision == Decision.BLOCK
        assert r.source == "rule"
        assert r.overridden
        assert r.model_decision == Decision.APPROVE
        assert any(h.rule == "card_blocked" for h in r.rules_fired)

    def test_watched_merchant_reviews(self, engine):
        r = engine.decide(payload(merchant="MERCH_WATCHED"), 0.001)
        assert r.decision == Decision.REVIEW
        assert r.source == "rule"

    def test_high_value_reviews(self, engine):
        r = engine.decide(payload(amount=250_000), 0.001)
        assert r.decision == Decision.REVIEW

    def test_very_high_value_blocks(self, engine):
        r = engine.decide(payload(amount=1_500_000), 0.001)
        assert r.decision == Decision.BLOCK

    def test_blocked_device(self, engine):
        engine.lists.blocked_devices.add("DEV_BAD")
        r = engine.decide(payload(device="DEV_BAD"), 0.001)
        assert r.decision == Decision.BLOCK


class TestTrustIsBounded:
    """An unbounded whitelist is an attack surface."""

    def test_trusted_card_lowers_review_to_approve(self, engine):
        r = engine.decide(payload(card="CARD_TRUSTED"), 0.02)
        assert r.decision == Decision.APPROVE
        assert r.source == "rule"

    def test_trusted_card_CANNOT_bypass_a_block_score(self, engine):
        """Trust is not a licence to ignore a strong fraud signal."""
        r = engine.decide(payload(card="CARD_TRUSTED"), 0.90)
        assert r.decision == Decision.BLOCK

    def test_trusted_card_CANNOT_bypass_a_value_limit(self, engine):
        """A regulatory limit is not waivable by trust."""
        r = engine.decide(payload(card="CARD_TRUSTED", amount=250_000), 0.001)
        assert r.decision == Decision.REVIEW

    def test_trusted_card_CANNOT_bypass_a_block_list(self, engine):
        """If a card is on both lists, blocked wins. Otherwise adding
        a card to the trusted list would un-block a stolen one."""
        engine.trust_card("CARD_STOLEN")
        r = engine.decide(payload(card="CARD_STOLEN"), 0.0001)
        assert r.decision == Decision.BLOCK


class TestPrecedence:
    """Most severe wins, and everything that fired is recorded."""

    def test_most_severe_rule_wins(self, engine):
        """high_value wants REVIEW, card_blocked wants BLOCK."""
        r = engine.decide(payload(card="CARD_STOLEN", amount=250_000), 0.001)
        assert r.decision == Decision.BLOCK
        assert len(r.rules_fired) >= 2

    def test_every_rule_is_recorded_not_just_the_winner(self, engine):
        """The audit trail should show everything that applied, not
        only the one that decided."""
        r = engine.decide(payload(merchant="MERCH_WATCHED",
                                  amount=250_000), 0.001)
        names = {h.rule for h in r.rules_fired}
        assert "merchant_watched" in names
        assert "high_value" in names

    def test_rule_cannot_lower_a_model_block(self, engine):
        """A REVIEW rule must not soften a BLOCK score."""
        r = engine.decide(payload(amount=250_000), 0.90)
        assert r.decision == Decision.BLOCK

    def test_severity_order(self):
        assert SEVERITY[Decision.BLOCK] > SEVERITY[Decision.REVIEW]
        assert SEVERITY[Decision.REVIEW] > SEVERITY[Decision.APPROVE]


class TestExplanation:
    """Every decision must say why."""

    def test_model_decision_names_the_score(self, engine):
        r = engine.decide(payload(), 0.001)
        assert "0.001" in r.explain() or "p=" in r.explain()

    def test_rule_decision_names_the_rule(self, engine):
        r = engine.decide(payload(card="CARD_STOLEN"), 0.0001)
        assert "card_blocked" in r.explain()

    def test_override_is_visible_in_the_explanation(self, engine):
        r = engine.decide(payload(card="CARD_STOLEN"), 0.0001)
        assert "overriding" in r.explain()

    def test_result_serialises(self, engine):
        """The API returns this as JSON, so it must survive asdict."""
        d = engine.decide(payload(card="CARD_STOLEN"), 0.0001).to_dict()
        assert d["decision"] == "block"
        assert isinstance(d["rules_fired"], list)
        assert d["rules_fired"][0]["rule"]


class TestStats:
    def test_counts_track_decisions(self, engine):
        engine.decide(payload(), 0.001)
        engine.decide(payload(), 0.50)
        s = engine.stats()
        assert s["total"] == 2
        assert s["decisions"]["approve"] == 1
        assert s["decisions"]["block"] == 1

    def test_override_rate(self, engine):
        engine.decide(payload(), 0.001)
        engine.decide(payload(card="CARD_STOLEN"), 0.001)
        s = engine.stats()
        assert s["overrides"] == 1
        assert s["override_rate"] == pytest.approx(0.5)