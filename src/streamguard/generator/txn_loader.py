"""
Insert generated transactions into PostgreSQL.

Resolves business references (CUST000042, MERCH000117) to integer
foreign keys, then bulk-inserts in batches. Designed to be called
once per simulated day so memory stays flat.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, text

from streamguard.db.models import Card, Customer, Device, Merchant, Transaction
from streamguard.db.session import get_session
from streamguard.generator.transactions import GenTransaction
from streamguard.utils.logging_config import get_logger

log = get_logger(__name__)

BATCH_SIZE = 5_000


class TransactionLoader:
    """
    Loads transactions, resolving refs to database ids.

    The ref->id maps are fetched ONCE at construction. Looking them up
    per transaction would mean 700,000 queries; holding ~22,000 small
    entries in a dict costs a few megabytes and makes it free.
    """

    def __init__(self) -> None:
        self.customer_ids = self._fetch_map(Customer.customer_ref, Customer.id)
        self.card_ids = self._fetch_map(Card.card_ref, Card.id)
        self.merchant_ids = self._fetch_map(Merchant.merchant_ref, Merchant.id)
        self.device_ids = self._fetch_map(Device.device_ref, Device.id)

        self.inserted = 0
        self.skipped = 0

        log.info(
            "transaction_loader_ready",
            customers=len(self.customer_ids),
            cards=len(self.card_ids),
            merchants=len(self.merchant_ids),
            devices=len(self.device_ids),
        )

    @staticmethod
    def _fetch_map(ref_column, id_column) -> dict[str, int]:
        with get_session() as db:
            rows = db.execute(select(ref_column, id_column)).all()
        return {ref: db_id for ref, db_id in rows}

    # ---------- Insertion ----------

    def insert_batch(self, transactions: list[GenTransaction]) -> int:
        """Insert one batch. Returns the number of rows written."""
        if not transactions:
            return 0

        now = datetime.now(timezone.utc)
        rows: list[dict] = []

        for txn in transactions:
            customer_id = self.customer_ids.get(txn.customer_ref)
            card_id = self.card_ids.get(txn.card_ref)
            merchant_id = self.merchant_ids.get(txn.merchant_ref)

            # A transaction referencing an entity that does not exist
            # would violate a foreign key and abort the whole batch.
            # Skip and count instead -- then investigate if the count
            # is ever non-zero.
            if customer_id is None or card_id is None or merchant_id is None:
                self.skipped += 1
                continue

            device_id = (
                self.device_ids.get(txn.device_ref) if txn.device_ref else None
            )

            rows.append({
                "transaction_ref": txn.transaction_ref,
                "occurred_at": txn.occurred_at,
                "card_id": card_id,
                "customer_id": customer_id,
                "merchant_id": merchant_id,
                "device_id": device_id,
                "amount": txn.amount,
                "currency": txn.currency,
                "channel": txn.channel,
                "entry_mode": txn.entry_mode,
                "city": txn.city,
                "country": txn.country,
                "lat": txn.lat,
                "lon": txn.lon,
                "is_fraud": txn.is_fraud,
                "fraud_type": txn.fraud_type,
                "ingested_at": now,
            })

        if not rows:
            return 0

        with get_session() as db:
            for start in range(0, len(rows), BATCH_SIZE):
                db.execute(
                    Transaction.__table__.insert(), rows[start:start + BATCH_SIZE]
                )

        self.inserted += len(rows)
        return len(rows)

    # ---------- Maintenance ----------

    @staticmethod
    def truncate_transactions() -> None:
        """Clear transactions and everything that depends on them."""
        with get_session() as db:
            db.execute(text(
                "TRUNCATE TABLE case_events, cases, decisions, transactions "
                "RESTART IDENTITY CASCADE"
            ))
        log.warning("transactions_truncated")

    @staticmethod
    def analyze() -> None:
        """
        Update PostgreSQL's table statistics.

        The query planner decides whether to use an index based on
        statistics about the data. After a bulk load those statistics
        are stale, and the planner may ignore your carefully designed
        composite indexes. ANALYZE refreshes them.
        """
        with get_session() as db:
            db.execute(text("ANALYZE transactions"))
        log.info("transactions_analyzed")