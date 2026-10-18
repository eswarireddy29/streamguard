"""
Persist a generated Population into PostgreSQL.

Inserts in dependency order (customers -> cards, merchants, devices)
and builds reference-to-id maps so later stages can resolve foreign keys.
"""

from __future__ import annotations

from sqlalchemy import delete, select, text

from streamguard.db.models import Card, Customer, Device, Merchant
from streamguard.db.session import get_session
from streamguard.generator.entities import Population
from streamguard.utils.logging_config import get_logger

log = get_logger(__name__)

# Insert in batches rather than one row at a time. One INSERT per row
# across 12,000 rows means 12,000 network round trips; batching cuts
# that to a few dozen.
BATCH_SIZE = 2_000


class ReferenceLoader:
    """Loads reference entities and returns ref -> database id maps."""

    def __init__(self) -> None:
        self.customer_ids: dict[str, int] = {}
        self.card_ids: dict[str, int] = {}
        self.merchant_ids: dict[str, int] = {}
        self.device_ids: dict[str, int] = {}

    # ---------- Clearing ----------

    def truncate_all(self) -> None:
        """
        Remove all data from every table.

        TRUNCATE ... CASCADE is far faster than DELETE for emptying
        tables, and RESTART IDENTITY resets the auto-increment counters
        so ids start from 1 again on each regeneration.
        """
        with get_session() as db:
            db.execute(text(
                "TRUNCATE TABLE case_events, cases, decisions, transactions, "
                "cards, devices, merchants, customers "
                "RESTART IDENTITY CASCADE"
            ))
        log.warning("all_tables_truncated")

    # ---------- Loading ----------

    def load(self, population: Population, truncate: bool = True) -> dict[str, int]:
        if truncate:
            self.truncate_all()

        self._load_customers(population)
        self._load_cards(population)
        self._load_merchants(population)
        self._load_devices(population)

        counts = {
            "customers": len(self.customer_ids),
            "cards": len(self.card_ids),
            "merchants": len(self.merchant_ids),
            "devices": len(self.device_ids),
        }
        log.info("reference_data_loaded", **counts)
        return counts

    def _load_customers(self, population: Population) -> None:
        rows = [
            {
                "customer_ref": c.customer_ref,
                "full_name": c.full_name,
                "email": c.email,
                "home_city": c.home_city,
                "home_country": c.home_country,
                "home_lat": c.home_lat,
                "home_lon": c.home_lon,
                "account_opened_at": c.account_opened_at,
                "risk_band": c.risk_band,
                "avg_monthly_spend": c.avg_monthly_spend,
                "typical_txn_amount": c.typical_txn_amount,
            }
            for c in population.customers
        ]
        self._bulk_insert(Customer, rows, "customers")
        self.customer_ids = self._fetch_id_map(Customer, Customer.customer_ref)

    def _load_cards(self, population: Population) -> None:
        rows = [
            {
                "card_ref": c.card_ref,
                "customer_id": self.customer_ids[c.customer_ref],
                "last_four": c.last_four,
                "card_type": c.card_type,
                "issued_at": c.issued_at,
                "is_active": c.is_active,
                "credit_limit": c.credit_limit,
            }
            for c in population.cards
        ]
        self._bulk_insert(Card, rows, "cards")
        self.card_ids = self._fetch_id_map(Card, Card.card_ref)

    def _load_merchants(self, population: Population) -> None:
        rows = [
            {
                "merchant_ref": m.merchant_ref,
                "name": m.name,
                "mcc": m.mcc,
                "category": m.category,
                "city": m.city,
                "country": m.country,
                "lat": m.lat,
                "lon": m.lon,
                "risk_score": m.risk_score,
                "is_online": m.is_online,
            }
            for m in population.merchants
        ]
        self._bulk_insert(Merchant, rows, "merchants")
        self.merchant_ids = self._fetch_id_map(Merchant, Merchant.merchant_ref)

    def _load_devices(self, population: Population) -> None:
        # owner_ref and is_personal are deliberately NOT persisted.
        # See the note in the task description: ownership is a generator
        # concept, and is_personal is derivable from device_type.
        rows = [
            {
                "device_ref": d.device_ref,
                "device_type": d.device_type,
                "os_family": d.os_family,
                "fingerprint": d.fingerprint,
                "first_seen_at": d.first_seen_at,
            }
            for d in population.devices
        ]
        self._bulk_insert(Device, rows, "devices")
        self.device_ids = self._fetch_id_map(Device, Device.device_ref)

    # ---------- Mechanics ----------

    def _bulk_insert(self, model, rows: list[dict], label: str) -> None:
        if not rows:
            log.warning("nothing_to_insert", table=label)
            return

        with get_session() as db:
            for start in range(0, len(rows), BATCH_SIZE):
                batch = rows[start:start + BATCH_SIZE]
                db.execute(model.__table__.insert(), batch)

        log.info("rows_inserted", table=label, count=len(rows))

    def _fetch_id_map(self, model, ref_column) -> dict[str, int]:
        """Build {business_ref: database_id} so foreign keys can be resolved."""
        with get_session() as db:
            result = db.execute(select(ref_column, model.id)).all()
        return {ref: db_id for ref, db_id in result}