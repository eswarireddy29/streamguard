"""
src/streamguard/api/cases.py

Task 22 - persisting decisions and running the analyst queue.

Until now a score vanished after the HTTP response. Three things need
it to persist:

  1. An analyst must be able to work a queue of flagged transactions.
  2. Their verdict is the ONLY ground truth this system will ever get
     after deployment - Task 30 retrains from exactly these labels.
  3. An audit trail must answer "who decided what, when, and why",
     which is a regulatory requirement, not a nice-to-have.

The Task 4B schema was designed for this: `decisions` stores the
features as JSONB (so training/serving skew can be DETECTED later -
you can only detect it if you recorded it), `cases` holds the queue,
and `case_events` is the append-only audit log.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import text

from streamguard.db.session import get_session
from streamguard.utils.logging_config import get_logger

log = get_logger(__name__)


class Verdict:
    """What an analyst concluded. These become training labels."""
    PENDING = "pending"
    CONFIRMED_FRAUD = "confirmed_fraud"
    LEGITIMATE = "legitimate"
    INCONCLUSIVE = "inconclusive"

    ALL = {PENDING, CONFIRMED_FRAUD, LEGITIMATE, INCONCLUSIVE}

    # Only these two are usable as labels. "inconclusive" is NOT
    # treated as legitimate - an analyst who could not decide has not
    # told you the transaction was fine, and training on it as a
    # negative would teach the model that genuine fraud is normal.
    LABELLED = {CONFIRMED_FRAUD, LEGITIMATE}


class CaseStatus:
    OPEN = "open"
    IN_REVIEW = "in_review"
    CLOSED = "closed"


@dataclass
class CaseRecord:
    """One case as an analyst sees it."""
    case_ref: str
    transaction_ref: str
    status: str
    priority: int
    score: float
    action: str
    amount: float
    occurred_at: datetime
    assigned_to: str | None
    verdict: str
    explanation: dict | None

    def to_dict(self) -> dict:
        d = {k: getattr(self, k) for k in self.__dataclass_fields__}
        d["occurred_at"] = (self.occurred_at.isoformat()
                            if self.occurred_at else None)
        return d


def _priority(score: float, amount: float) -> int:
    """Queue order: 1 is most urgent.

    Score alone is the wrong sort. A 0.95 score on a Rs 50 card-testing
    probe costs Rs 50; a 0.40 score on Rs 200,000 costs 4,000 times
    more. Analyst time should go where the money is, so priority
    combines likelihood with exposure - the same reasoning as the
    Task 16 cost threshold.
    """
    exposure = score * amount
    if exposure >= 50_000:
        return 1
    if exposure >= 10_000:
        return 2
    if exposure >= 1_000:
        return 3
    return 4


class CaseRepository:
    """Reads and writes decisions, cases and audit events."""

    # ---------- writing ----------
    def record_decision(self, transaction_ref: str, result: dict,
                        features: dict, open_case: bool = True) -> dict:
        """Persist one scoring result, and open a case if it was flagged.

        An APPROVED transaction still gets a decision row - that is the
        record of what the system did, and Task 30 needs the approved
        population to measure false negatives. Only a flagged one gets
        a case, because only that needs human time.
        """
        with get_session() as s:
            txn = s.execute(
                text("SELECT id, amount FROM transactions "
                     "WHERE transaction_ref = :r"),
                {"r": transaction_ref},
            ).fetchone()

            if txn is None:
                # A transaction scored live may not be in the database
                # yet. Recording a decision that points at nothing
                # would corrupt the audit trail, so this is reported
                # rather than silently skipped.
                return {"recorded": False,
                        "reason": "transaction_ref not found in database"}

            txn_id, amount = txn[0], float(txn[1])

            decision_id = s.execute(
                text("""
                    INSERT INTO decisions
                        (transaction_id, model_version, score, action,
                         threshold_review, threshold_block, features,
                         explanation, latency_ms, decided_at)
                    VALUES
                        (:txn, :mv, :score, :action, :tr, :tb,
                         CAST(:feat AS jsonb), CAST(:expl AS jsonb),
                         :lat, :at)
                    RETURNING id
                """),
                {
                    "txn": txn_id,
                    "mv": result.get("model_version", "unknown"),
                    "score": float(result.get("probability", 0.0)),
                    "action": result.get("decision", "approve"),
                    "tr": float(result.get("threshold_review", 0.0)),
                    "tb": float(result.get("threshold_used", 0.0)),
                    "feat": json.dumps(features),
                    "expl": json.dumps({
                        "top_reasons": result.get("top_reasons", []),
                        "rules_fired": result.get("rules_fired", []),
                        "decision_source": result.get("decision_source"),
                        "model_decision": result.get("model_decision"),
                        "overridden": result.get("overridden", False),
                    }),
                    "lat": float(result.get("latency_ms", 0.0)),
                    "at": datetime.now(timezone.utc),
                },
            ).scalar()

            action = result.get("decision", "approve")
            case_ref = None

            if open_case and action in ("review", "block"):
                score = float(result.get("probability", 0.0))
                case_ref = f"CASE{decision_id:010d}"
                case_id = s.execute(
                    text("""
                        INSERT INTO cases
                            (case_ref, transaction_id, decision_id, status,
                             priority, verdict, created_at, updated_at)
                        VALUES
                            (:ref, :txn, :dec, :st, :pri, :verdict,
                             :now, :now)
                        RETURNING id
                    """),
                    {
                        "ref": case_ref, "txn": txn_id, "dec": decision_id,
                        "st": CaseStatus.OPEN,
                        "pri": _priority(score, amount),
                        "verdict": Verdict.PENDING,
                        "now": datetime.now(timezone.utc),
                    },
                ).scalar()

                self._event(s, case_id, "case_opened", "system", {
                    "score": score, "action": action,
                    "decision_source": result.get("decision_source"),
                })

            return {"recorded": True, "decision_id": decision_id,
                    "case_ref": case_ref, "action": action}

    def _event(self, session, case_id: int, event_type: str,
               actor: str, payload: dict) -> None:
        """Append to the audit log. Never updated, never deleted."""
        session.execute(
            text("""
                INSERT INTO case_events
                    (case_id, event_type, actor, payload, occurred_at)
                VALUES (:cid, :et, :actor, CAST(:p AS jsonb), :at)
            """),
            {"cid": case_id, "et": event_type, "actor": actor,
             "p": json.dumps(payload), "at": datetime.now(timezone.utc)},
        )

    # ---------- the queue ----------

    def queue(self, limit: int = 50, status: str = CaseStatus.OPEN,
              assigned_to: str | None = None) -> list:
        """Cases waiting for an analyst, most urgent first."""
        sql = """
            SELECT c.case_ref, t.transaction_ref, c.status, c.priority,
                   d.score, d.action, t.amount, t.occurred_at,
                   c.assigned_to, c.verdict, d.explanation
            FROM cases c
            JOIN transactions t ON t.id = c.transaction_id
            JOIN decisions d ON d.id = c.decision_id
            WHERE c.status = :st
        """
        params = {"st": status, "lim": limit}
        if assigned_to:
            sql += " AND c.assigned_to = :who"
            params["who"] = assigned_to
        sql += " ORDER BY c.priority ASC, d.score DESC LIMIT :lim"

        with get_session() as s:
            rows = s.execute(text(sql), params).fetchall()

        return [CaseRecord(
            case_ref=r[0], transaction_ref=r[1], status=r[2],
            priority=r[3], score=float(r[4]), action=r[5],
            amount=float(r[6]), occurred_at=r[7], assigned_to=r[8],
            verdict=r[9], explanation=r[10],
        ) for r in rows]

    def get(self, case_ref: str) -> dict | None:
        """One case with its full audit trail."""
        with get_session() as s:
            row = s.execute(
                text("""
                    SELECT c.id, c.case_ref, t.transaction_ref, c.status,
                           c.priority, d.score, d.action, t.amount,
                           t.occurred_at, c.assigned_to, c.verdict,
                           c.notes, d.explanation, d.features,
                           d.model_version
                    FROM cases c
                    JOIN transactions t ON t.id = c.transaction_id
                    JOIN decisions d ON d.id = c.decision_id
                    WHERE c.case_ref = :ref
                """),
                {"ref": case_ref},
            ).fetchone()

            if row is None:
                return None

            events = s.execute(
                text("""
                    SELECT event_type, actor, payload, occurred_at
                    FROM case_events WHERE case_id = :cid
                    ORDER BY occurred_at ASC, id ASC
                """),
                {"cid": row[0]},
            ).fetchall()

        return {
            "case_ref": row[1], "transaction_ref": row[2],
            "status": row[3], "priority": row[4], "score": float(row[5]),
            "action": row[6], "amount": float(row[7]),
            "occurred_at": row[8].isoformat() if row[8] else None,
            "assigned_to": row[9], "verdict": row[10], "notes": row[11],
            "explanation": row[12], "model_version": row[14],
            "n_features": len(row[13]) if row[13] else 0,
            "audit_trail": [
                {"event": e[0], "actor": e[1], "payload": e[2],
                 "at": e[3].isoformat()} for e in events
            ],
        }

    # ---------- analyst actions ----------

    def assign(self, case_ref: str, analyst: str) -> dict:
        with get_session() as s:
            row = s.execute(
                text("SELECT id, status FROM cases WHERE case_ref = :r"),
                {"r": case_ref},
            ).fetchone()
            if row is None:
                return {"ok": False, "reason": "case not found"}
            if row[1] == CaseStatus.CLOSED:
                return {"ok": False, "reason": "case is already closed"}

            s.execute(
                text("""UPDATE cases SET assigned_to = :who,
                        status = :st, updated_at = :now
                        WHERE id = :cid"""),
                {"who": analyst, "st": CaseStatus.IN_REVIEW,
                 "now": datetime.now(timezone.utc), "cid": row[0]},
            )
            self._event(s, row[0], "assigned", analyst, {"to": analyst})

        return {"ok": True, "case_ref": case_ref, "assigned_to": analyst}

    def submit_verdict(self, case_ref: str, analyst: str, verdict: str,
                       notes: str = "") -> dict:
        """Close a case with an analyst's conclusion.

        THIS IS THE LABEL. After deployment there is no other source of
        truth - Task 30 retrains on exactly these verdicts. A careless
        verdict becomes a training error, which is why the audit trail
        records who submitted it.
        """
        if verdict not in Verdict.ALL:
            return {"ok": False,
                    "reason": f"verdict must be one of {sorted(Verdict.ALL)}"}

        with get_session() as s:
            row = s.execute(
                text("SELECT id, status, verdict FROM cases "
                     "WHERE case_ref = :r"),
                {"r": case_ref},
            ).fetchone()
            if row is None:
                return {"ok": False, "reason": "case not found"}
            if row[1] == CaseStatus.CLOSED:
                return {"ok": False,
                        "reason": f"case already closed with verdict "
                                  f"'{row[2]}'"}

            now = datetime.now(timezone.utc)
            s.execute(
                text("""UPDATE cases
                        SET verdict = :v, verdict_at = :now,
                            status = :st, notes = :notes,
                            assigned_to = COALESCE(assigned_to, :who),
                            updated_at = :now
                        WHERE id = :cid"""),
                {"v": verdict, "now": now, "st": CaseStatus.CLOSED,
                 "notes": notes or None, "who": analyst, "cid": row[0]},
            )
            self._event(s, row[0], "verdict_submitted", analyst, {
                "verdict": verdict, "notes": notes,
                "usable_as_label": verdict in Verdict.LABELLED,
            })

        return {"ok": True, "case_ref": case_ref, "verdict": verdict,
                "usable_as_label": verdict in Verdict.LABELLED}

    # ---------- reporting ----------

    def stats(self) -> dict:
        with get_session() as s:
            d = s.execute(text("""
                SELECT action, COUNT(*), AVG(score), AVG(latency_ms)
                FROM decisions GROUP BY action
            """)).fetchall()

            c = s.execute(text("""
                SELECT status, verdict, COUNT(*) FROM cases
                GROUP BY status, verdict
            """)).fetchall()

            labels = s.execute(text("""
                SELECT verdict, COUNT(*) FROM cases
                WHERE verdict IN ('confirmed_fraud', 'legitimate')
                GROUP BY verdict
            """)).fetchall()

            events = s.execute(
                text("SELECT COUNT(*) FROM case_events")).scalar()

        return {
            "decisions": [
                {"action": r[0], "n": r[1], "mean_score": float(r[2] or 0),
                 "mean_latency_ms": float(r[3] or 0)} for r in d
            ],
            "cases": [{"status": r[0], "verdict": r[1], "n": r[2]}
                      for r in c],
            "labels_available": {r[0]: r[1] for r in labels},
            "audit_events": events,
        }

    def recent_decisions(self, limit: int = 50,
                         since_id: int = 0) -> dict:
        """Decisions newest-first, for the live stream page.

        `since_id` lets the client ask only for what it has not seen.
        Re-sending the whole window every poll would grow the payload
        with the table and make the page slower the longer it runs.
        """
        with get_session() as s:
            rows = s.execute(
                text("""
                    SELECT d.id, t.transaction_ref, d.score, d.action,
                           t.amount, t.city, t.country, t.channel,
                           t.entry_mode, t.occurred_at, d.decided_at,
                           d.latency_ms, d.model_version,
                           c.case_ref
                    FROM decisions d
                    JOIN transactions t ON t.id = d.transaction_id
                    LEFT JOIN cases c ON c.decision_id = d.id
                    WHERE d.id > :since
                    ORDER BY d.id DESC
                    LIMIT :lim
                """),
                {"since": since_id, "lim": limit},
            ).fetchall()

            totals = s.execute(text("""
                SELECT action, COUNT(*), AVG(latency_ms)
                FROM decisions GROUP BY action
            """)).fetchall()

        return {
            "decisions": [{
                "id": r[0], "transaction_ref": r[1], "score": float(r[2]),
                "action": r[3], "amount": float(r[4]), "city": r[5],
                "country": r[6], "channel": r[7], "entry_mode": r[8],
                "occurred_at": r[9].isoformat() if r[9] else None,
                "decided_at": r[10].isoformat() if r[10] else None,
                "latency_ms": float(r[11]), "model_version": r[12],
                "case_ref": r[13],
            } for r in rows],
            "totals": {r[0]: {"n": r[1], "mean_latency_ms": float(r[2] or 0)}
                       for r in totals},
            "max_id": max((r[0] for r in rows), default=since_id),
        }

    def risk_kpis(self, fn_cost: float = 5000.0,
                  fp_cost: float = 200.0) -> dict:
        """What a risk manager needs: money, mix, and label supply.

        The cost figures are the Task 16 assumptions. They are passed
        in rather than hardcoded so the page can be re-run with the
        bank's real chargeback and churn numbers.

        MONEY IS ESTIMATED, NOT MEASURED. Only closed cases have a
        verdict, so "fraud prevented" counts blocked transactions an
        analyst CONFIRMED. Blocked-and-unreviewed is not counted as a
        win - claiming it would be marking our own homework.
        """
        with get_session() as s:
            mix = s.execute(text("""
                SELECT action, COUNT(*), AVG(score), SUM(t.amount)
                FROM decisions d
                JOIN transactions t ON t.id = d.transaction_id
                GROUP BY action
            """)).fetchall()

            # Decisions per hour, for the trend chart.
            hourly = s.execute(text("""
                SELECT date_trunc('hour', decided_at) AS h,
                       action, COUNT(*)
                FROM decisions
                GROUP BY h, action
                ORDER BY h
            """)).fetchall()

            # Score distribution in 10 buckets. Quantile bucketing
            # would hide the shape: at this prevalence almost
            # everything sits near zero, and that IS the finding.
            buckets = s.execute(text("""
                SELECT width_bucket(score, 0, 1, 10) AS b,
                       COUNT(*), MIN(score), MAX(score)
                FROM decisions
                GROUP BY b ORDER BY b
            """)).fetchall()

            verdicts = s.execute(text("""
                SELECT c.verdict, COUNT(*), SUM(t.amount)
                FROM cases c
                JOIN transactions t ON t.id = c.transaction_id
                GROUP BY c.verdict
            """)).fetchall()

            # Confirmed outcomes only - the basis for the money figures.
            confirmed = s.execute(text("""
                SELECT d.action, c.verdict, COUNT(*), SUM(t.amount)
                FROM cases c
                JOIN decisions d ON d.id = c.decision_id
                JOIN transactions t ON t.id = c.transaction_id
                WHERE c.verdict IN ('confirmed_fraud', 'legitimate')
                GROUP BY d.action, c.verdict
            """)).fetchall()

            latency = s.execute(text("""
                SELECT AVG(latency_ms),
                       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY latency_ms),
                       PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms),
                       PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY latency_ms),
                       MAX(latency_ms), COUNT(*)
                FROM decisions
            """)).fetchone()

            queue = s.execute(text("""
                SELECT status, COUNT(*) FROM cases GROUP BY status
            """)).fetchall()

            models = s.execute(text("""
                SELECT model_version, COUNT(*), MIN(decided_at), MAX(decided_at)
                FROM decisions GROUP BY model_version
            """)).fetchall()

        # --- money, from CONFIRMED verdicts only ---
        prevented = sum(float(r[3] or 0) for r in confirmed
                        if r[1] == "confirmed_fraud")
        prevented_n = sum(r[2] for r in confirmed
                          if r[1] == "confirmed_fraud")
        false_alarms = sum(r[2] for r in confirmed if r[1] == "legitimate")
        fa_cost = false_alarms * fp_cost

        return {
            "mix": [{"action": r[0], "n": r[1], "mean_score": float(r[2] or 0),
                     "total_amount": float(r[3] or 0)} for r in mix],
            "hourly": [{"hour": r[0].isoformat(), "action": r[1], "n": r[2]}
                       for r in hourly],
            "score_buckets": [{"bucket": r[0], "n": r[1],
                               "lo": float(r[2] or 0), "hi": float(r[3] or 0)}
                              for r in buckets],
            "verdicts": [{"verdict": r[0], "n": r[1],
                          "amount": float(r[2] or 0)} for r in verdicts],
            "queue": {r[0]: r[1] for r in queue},
            "money": {
                "fraud_prevented_amount": prevented,
                "fraud_prevented_n": prevented_n,
                "false_alarms_n": false_alarms,
                "false_alarm_cost": fa_cost,
                "net": prevented - fa_cost,
                "fn_cost_assumption": fn_cost,
                "fp_cost_assumption": fp_cost,
                "basis": "confirmed analyst verdicts only",
            },
            "latency": {
                "mean_ms": float(latency[0] or 0),
                "p50_ms": float(latency[1] or 0),
                "p95_ms": float(latency[2] or 0),
                "p99_ms": float(latency[3] or 0),
                "max_ms": float(latency[4] or 0),
                "n": latency[5],
            },
            "models": [{"version": r[0], "n": r[1],
                        "first": r[2].isoformat() if r[2] else None,
                        "last": r[3].isoformat() if r[3] else None}
                       for r in models],
        }