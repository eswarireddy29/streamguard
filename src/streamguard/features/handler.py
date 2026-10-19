"""
Stream handler that computes features and writes them to Parquet.

Plugs into the Task 9 StreamProcessor. This is where the feature
engine meets the stream: one handler, registered on the processor,
called once per event in order.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from streamguard.eventlog.event import Event
from streamguard.eventlog.handlers import EventHandler
from streamguard.features.computer import FeatureComputer
from streamguard.features.state import StateStore
from streamguard.features.writer import FeatureWriter
from streamguard.utils.logging_config import get_logger

log = get_logger(__name__)


class FeatureHandler(EventHandler):
    """
    Computes features for each transaction event and writes a row.

    The processor calls handle() once per event, in log order, which
    is exactly what the feature engine requires.
    """

    def __init__(
        self,
        output_path: Path,
        store: StateStore | None = None,
        name: str = "features",
    ):
        super().__init__(name)
        self.store = store or StateStore()
        self.computer = FeatureComputer(self.store)
        self.writer = FeatureWriter(output_path)

        # Diagnostics
        self.max_deque_len = 0
        self.max_count_24h = 0

    def handle(self, event: Event) -> None:
        payload = event.payload

        # process() enforces the ordering: features computed from
        # state containing only the past, THEN state updated.
        features = self.computer.process(payload)

        occurred_at = payload["occurred_at"]
        if isinstance(occurred_at, str):
            occurred_at = datetime.fromisoformat(occurred_at)

        row = {
            "transaction_ref": payload["transaction_ref"],
            "occurred_at": occurred_at,
            "card_ref": payload["card_ref"],
            "customer_ref": payload["customer_ref"],
            "merchant_ref": payload["merchant_ref"],
            "event_offset": event.offset,
            # Labels, for training only
            "is_fraud": bool(payload.get("is_fraud", False)),
            "fraud_type": payload.get("fraud_type", "none"),
        }
        row.update(features)

        self.writer.add(row)

        # Track whether RECENT_WINDOW = 50 was ever a binding
        # constraint. If a card hits 50 in its deque while its 24h
        # count also reaches 50, the window was silently truncated
        # and the velocity features for that card are understated.
        card = self.store.card(payload["card_ref"])
        if len(card.recent) > self.max_deque_len:
            self.max_deque_len = len(card.recent)
        count_24h = features.get("txn_count_24h", 0)
        if count_24h > self.max_count_24h:
            self.max_count_24h = int(count_24h)

    def on_stop(self) -> None:
        """
        Flush the final partial chunk.

        Without this the last fewer-than-50,000 rows are lost
        silently. The processor calls on_stop() from a finally block,
        so this runs even after a crash.
        """
        self.writer.close()
        log.info(
            "feature_handler_stopped",
            rows=self.writer.rows_written,
            max_deque=self.max_deque_len,
            max_24h_count=self.max_count_24h,
            **self.store.summary(),
        )