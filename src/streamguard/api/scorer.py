"""
src/streamguard/api/scorer.py

Task 19 - the thing that actually scores a transaction.

ARCHITECTURE DECISION (Option A, chosen at Task 19): feature state
lives IN MEMORY, warmed at startup by replaying the event log.

Why: the feature engine is stateful - compute_features() reads this
card's running mean, its last location, its 5-minute velocity. That
state has to come from somewhere. The alternatives were a database
query per request (durable, but puts a round-trip inside the latency
budget Task 20 is about to measure) or having the client send
precomputed features (fast, but moves training/serving skew to the
client, which is the exact failure this project exists to address).

Cost of this choice, stated plainly:
  - state is lost on restart; warm-up takes minutes
  - one process only, no horizontal scaling
  - Task 20 should measure the alternative and show the difference
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from streamguard.eventlog.consumer import FileEventConsumer
from streamguard.ml.splitter import PROJECT_ROOT
from streamguard.features.computer import FeatureComputer
from streamguard.features.state import StateStore
from streamguard.features.graph import TransactionGraph, GRAPH_FEATURE_NAMES
from streamguard.api.decisions import DecisionEngine, DecisionConfig
from streamguard.api.observability import metrics
from streamguard.utils.logging_config import get_logger

log = get_logger(__name__)


@dataclass
class ScorerConfig:
    model_path: Path
    threshold_block: float = 0.03061      # Task 16 cost optimum
    threshold_review: float = 0.01113     # Task 16 three-way band
    warm_events: int = 0                  # 0 = the whole log
    explain: bool = True
    topic: str = "transactions"


class Scorer:
    """Model + feature state + graph, ready to score one transaction."""

    def __init__(self, config: ScorerConfig):
        self.cfg = config
        self.booster = lgb.Booster(model_file=str(config.model_path))
        self.feature_names = list(self.booster.feature_name())
        self.model_version = config.model_path.stem

        self.store = StateStore()
        self.computer = FeatureComputer(self.store)
        self.graph = TransactionGraph(ring_hops=1, ring_cap=50)
        # Task 21: the decision is policy, not a model output. Rules
        # that the model cannot learn - a stolen-card report, a
        # regulatory value limit - are applied here, and every decision
        # records which rule or threshold produced it.
        self.engine = DecisionEngine(DecisionConfig(
            threshold_block=config.threshold_block,
            threshold_review=config.threshold_review,
        ))
        # Which of the model's columns come from the graph, and which
        # from the per-transaction computer. The model was trained on a
        # specific ordered list; we must rebuild that exact order.
        self.graph_cols = [c for c in self.feature_names
                           if c in GRAPH_FEATURE_NAMES]
        self.base_cols = [c for c in self.feature_names
                          if c not in GRAPH_FEATURE_NAMES]

        self.explainer = None
        if config.explain:
            import shap
            self.explainer = shap.TreeExplainer(self.booster)

        self.warm_events = 0
        self.warm_seconds = 0.0
        self.warmed_from = "not warmed"
        self.scored = 0
        self.started = time.time()

        # Seen transaction refs, for idempotency. Task 8 established
        # that consumers must be idempotent under at-least-once
        # delivery; the same applies here. Without it, a retried POST
        # folds the SAME transaction into state twice and the card
        # looks like it is being tested - velocity 3, zero distance
        # moved, implied speed at the 99,999 sentinel.
        # Bounded so a long-running process cannot grow without limit.
        self.seen: dict[str, dict] = {}
        self.seen_order: deque = deque(maxlen=100_000)
        self.duplicates = 0

    # ---------- startup ----------
    def warm(self) -> None:
        """Replay the event log to rebuild feature state.

        Events are consumed in log order, which is the same order the
        feature engine requires. A unique consumer group is used so
        this does not disturb the offsets of the Task 10 feature build.
        """
        t0 = time.perf_counter()
        root = PROJECT_ROOT / "data" / "events"
        consumer = FileEventConsumer(
            root,
            topic=self.cfg.topic,
            group=f"scorer_warm_{int(time.time())}",
            from_beginning=True,
        )

        n = 0
        limit = self.cfg.warm_events or None
        for event in consumer.stream():
            p = event.payload
            self.computer.process(p)
            self._graph_process(p)
            n += 1
            if n % 100_000 == 0:
                log.info("warming", events=n)
            if limit and n >= limit:
                break

        self.warm_events = n
        self.warm_seconds = time.perf_counter() - t0
        self.warmed_from = f"event log ({self.cfg.topic})"
        log.info("warm_complete", events=n,
                 seconds=round(self.warm_seconds, 1))

    def _graph_process(self, payload: dict) -> dict:
        from datetime import datetime
        when = payload["occurred_at"]
        if isinstance(when, str):
            when = datetime.fromisoformat(when)
        dev = payload.get("device_ref")
        return self.graph.process(
            str(payload["card_ref"]), str(payload["merchant_ref"]),
            str(dev) if dev else None, when,
        )

    # ---------- scoring ----------

    def score(self, payload: dict) -> dict:
        """Score one transaction and fold it into state.

        IDEMPOTENT: a transaction_ref already scored returns the cached
        result WITHOUT touching state. A retry must not make the card
        look busier than it is.

        THE ORDER MATTERS AND IS THE SAME AS TRAINING: features are
        computed from state containing only the past, then the state is
        updated. computer.process() and graph.process() each enforce
        that internally. Getting this backwards would be the Task 11
        self-leakage bug, live in production.
        """
        t0 = time.perf_counter()

        ref = str(payload.get("transaction_ref", ""))
        cached = self.seen.get(ref)
        if cached is not None:
            self.duplicates += 1
            metrics.duplicates += 1
            out = dict(cached)
            out["latency_ms"] = (time.perf_counter() - t0) * 1000
            out["duplicate"] = True
            return out

        t = time.perf_counter()
        base = self.computer.process(payload)
        metrics.record_stage("features", (time.perf_counter() - t) * 1000)

        t = time.perf_counter()
        graph = self._graph_process(payload)
        metrics.record_stage("graph", (time.perf_counter() - t) * 1000)

        merged = {**base, **graph}
        row = np.array([[merged.get(c, 0.0) for c in self.feature_names]],
                       dtype=np.float32)

        t = time.perf_counter()
        prob = float(self.booster.predict(row)[0])
        metrics.record_stage("predict", (time.perf_counter() - t) * 1000)
        outcome = self.engine.decide(payload, prob)
        decision = outcome.decision.value
        metrics.record_decision(decision)
        reasons = []
        explained = False
        if self.explainer is not None and decision != "approve":
            # Only explain what a human will look at. Explaining every
            # approved transaction would double the cost of the common
            # path for an explanation nobody reads.
            t = time.perf_counter()
            reasons = self._explain(row, merged)
            metrics.record_stage("shap", (time.perf_counter() - t) * 1000)
            explained = True
        result = {
            "probability": prob,
            "decision": decision,
            "threshold_used": self.cfg.threshold_block,
            "model_version": self.model_version,
            "n_features": len(self.feature_names),
            "latency_ms": (time.perf_counter() - t0) * 1000,
            "top_reasons": reasons,
            "explained": explained,
            "duplicate": False,
            "decision_source": outcome.source,
            "rules_fired": [r.to_dict() for r in outcome.rules_fired],
            "model_decision": outcome.model_decision.value,
            "overridden": outcome.overridden,
            "decision_explanation": outcome.explain(),
        }
        

        if ref:
            if len(self.seen_order) == self.seen_order.maxlen:
                self.seen.pop(self.seen_order[0], None)
            self.seen_order.append(ref)
            self.seen[ref] = result

        self.scored += 1
        return result

    def _explain(self, row: np.ndarray, merged: dict, top: int = 5) -> list:
        df = pd.DataFrame(row, columns=self.feature_names)
        vals = self.explainer.shap_values(df)
        if isinstance(vals, list):
            vals = vals[1] if len(vals) > 1 else vals[0]
        vals = np.asarray(vals)[0]

        pairs = [(self.feature_names[i],
                  float(merged.get(self.feature_names[i], 0.0)),
                  float(vals[i]))
                 for i in range(len(vals))]
        pairs = [p for p in pairs if p[2] > 0]
        pairs.sort(key=lambda p: -p[2])
        return [{"feature": f, "value": v, "shap": s}
                for f, v, s in pairs[:top]]

    # ---------- health ----------

    def health(self) -> dict:
        # StateStore exposes summary(), not a .cards attribute.
        summary = self.store.summary()
        cards = 0
        if isinstance(summary, dict):
            cards = int(summary.get("cards", summary.get("n_cards", 0)))

        return {
            "status": "ready" if self.warm_events else "cold",
            "model_version": self.model_version,
            "n_features": len(self.feature_names),
            "cards_in_state": cards,
            "merchants_in_state": len(self.graph.merchant_cards),
            "warmed_from": self.warmed_from,
            "warm_events": self.warm_events,
            "warm_seconds": self.warm_seconds,
            "uptime_seconds": time.time() - self.started,
            "scored": self.scored,
            "duplicates_rejected": self.duplicates,
            "decision_engine": self.engine.stats(),
        }