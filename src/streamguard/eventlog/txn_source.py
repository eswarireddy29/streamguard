"""
Read transactions from PostgreSQL and turn them into log events.

Streams with a server-side cursor so memory stays flat regardless of
table size, and emits strictly in chronological order -- which the
feature engine depends on.
"""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal

from sqlalchemy import select

from streamguard.db.models import Card, Customer, Device, Merchant, Transaction
from streamguard.db.session import engine
from streamguard.eventlog.event import Event, EventType
from streamguard.utils.logging_config import get_logger

log = get_logger(__name__)

# Rows fetched from PostgreSQL at a time. Large enough to amortise
# round trips, small enough that memory stays trivial.
FETCH_SIZE = 5_000


def _to_float(value) -> float:
    """Decimal is exact but not JSON-serialisable. Convert at the edge."""
    if isinstance(value, Decimal):
        return float(value)
    return float(value) if value is not None else 0.0


def stream_transaction_events() -> Iterator[Event]:
    """
    Yield one Event per transaction, oldest first.

    Joins to cards, customers, merchants and devices so the event
    carries business references (CARD0001234) rather than internal
    database ids. A real payment stream carries the former; the latter
    are an implementation detail of our storage.
    """
    stmt = (
        select(
            Transaction.transaction_ref,
            Transaction.occurred_at,
            Transaction.amount,
            Transaction.currency,
            Transaction.channel,
            Transaction.entry_mode,
            Transaction.city,
            Transaction.country,
            Transaction.lat,
            Transaction.lon,
            Transaction.is_fraud,
            Transaction.fraud_type,
            Card.card_ref,
            Card.card_type,
            Customer.customer_ref,
            Customer.home_city,
            Customer.home_country,
            Customer.home_lat,
            Customer.home_lon,
            Merchant.merchant_ref,
            Merchant.mcc,
            Merchant.category,
            Merchant.is_online,
            Merchant.city.label("merchant_city"),
            Merchant.country.label("merchant_country"),
            Device.device_ref,
            Device.device_type,
        )
        .join(Card, Card.id == Transaction.card_id)
        .join(Customer, Customer.id == Transaction.customer_id)
        .join(Merchant, Merchant.id == Transaction.merchant_id)
        .outerjoin(Device, Device.id == Transaction.device_id)
        # Chronological order is not optional. id breaks ties so the
        # ordering is deterministic across runs.
        .order_by(Transaction.occurred_at, Transaction.id)
    )

    # stream_results opens a server-side cursor: PostgreSQL keeps the
    # result set and sends rows in chunks, instead of shipping all
    # 791,112 rows into Python at once.
    conn = engine.connect().execution_options(
        stream_results=True, yield_per=FETCH_SIZE
    )

    try:
        for row in conn.execute(stmt):
            payload = {
                "transaction_ref": row.transaction_ref,
                "occurred_at": row.occurred_at.isoformat(),
                "card_ref": row.card_ref,
                "card_type": row.card_type,
                "customer_ref": row.customer_ref,
                "merchant_ref": row.merchant_ref,
                "device_ref": row.device_ref,
                "device_type": row.device_type,
                "amount": _to_float(row.amount),
                "currency": row.currency,
                "channel": row.channel,
                "entry_mode": row.entry_mode,
                # Where the transaction happened
                "city": row.city,
                "country": row.country,
                "lat": _to_float(row.lat),
                "lon": _to_float(row.lon),
                # Customer's home, for geo-distance features
                "home_city": row.home_city,
                "home_country": row.home_country,
                "home_lat": _to_float(row.home_lat),
                "home_lon": _to_float(row.home_lon),
                # Merchant attributes an acquirer would genuinely send.
                # NOTE: merchants.risk_score is deliberately EXCLUDED --
                # it is generator ground truth, and the model must learn
                # category risk from the MCC instead.
                "mcc": row.mcc,
                "merchant_category": row.category,
                "merchant_is_online": row.is_online,
                "merchant_city": row.merchant_city,
                "merchant_country": row.merchant_country,
                # GROUND TRUTH -- for training and evaluation ONLY.
                # The feature engine and scoring path must never read
                # these. Enforced by a test in Task 11.
                "is_fraud": row.is_fraud,
                "fraud_type": row.fraud_type,
            }

            yield Event(
                event_type=EventType.TRANSACTION.value,
                occurred_at=row.occurred_at,
                key=row.card_ref,
                payload=payload,
            )
    finally:
        # Always close, even if the caller abandons the iterator.
        # A leaked server-side cursor holds a PostgreSQL connection open.
        conn.close()


def count_transactions() -> int:
    """How many transactions exist, for progress reporting."""
    from sqlalchemy import func

    with engine.connect() as conn:
        return int(conn.execute(
            select(func.count()).select_from(Transaction)
        ).scalar_one())