"""
StreamGuard database schema.

Eight tables in three groups:
  Reference  : customers, cards, merchants, devices
  Core event : transactions
  System     : decisions, cases, case_events
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from streamguard.db.base import Base, TimestampMixin


# ============================================================
#  Enumerations
# ============================================================

class Channel(str, enum.Enum):
    """How the payment was made."""
    POS = "pos"
    ECOMMERCE = "ecommerce"
    ATM = "atm"
    CONTACTLESS = "contactless"
    RECURRING = "recurring"


class EntryMode(str, enum.Enum):
    """How the card details were captured."""
    CHIP = "chip"
    SWIPE = "swipe"
    MANUAL = "manual"
    NFC = "nfc"
    STORED_CREDENTIAL = "stored_credential"


class FraudType(str, enum.Enum):
    """Which fraud pattern produced this transaction (synthetic ground truth)."""
    NONE = "none"
    CARD_TESTING = "card_testing"
    ACCOUNT_TAKEOVER = "account_takeover"
    GEO_IMPOSSIBLE = "geo_impossible"
    MERCHANT_COLLUSION = "merchant_collusion"
    CARD_NOT_PRESENT = "card_not_present"


class DecisionAction(str, enum.Enum):
    """What the system decided to do."""
    APPROVE = "approve"
    REVIEW = "review"
    BLOCK = "block"


class CaseStatus(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    ESCALATED = "escalated"


class AnalystVerdict(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED_FRAUD = "confirmed_fraud"
    LEGITIMATE = "legitimate"
    INCONCLUSIVE = "inconclusive"


# Store enums as VARCHAR + CHECK constraint rather than native
# PostgreSQL enum types. Native enums are painful to modify in a
# migration; this form lets Alembic alter them cleanly.
def _enum(enum_cls, name: str) -> SAEnum:
    return SAEnum(enum_cls, name=name, native_enum=False, length=32,
                  values_callable=lambda e: [m.value for m in e])


# ============================================================
#  Reference tables
# ============================================================

class Customer(Base, TimestampMixin):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_ref: Mapped[str] = mapped_column(String(24), unique=True, index=True)

    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(160), nullable=False)

    # Home location — the anchor for geo-distance features
    home_city: Mapped[str] = mapped_column(String(80), nullable=False)
    home_country: Mapped[str] = mapped_column(String(2), nullable=False)
    home_lat: Mapped[float] = mapped_column(Float, nullable=False)
    home_lon: Mapped[float] = mapped_column(Float, nullable=False)

    # Behavioural profile — the generator uses these to produce
    # realistic spending, and they become model features.
    account_opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    risk_band: Mapped[str] = mapped_column(String(16), nullable=False, default="low")
    avg_monthly_spend: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    typical_txn_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)

    cards: Mapped[list[Card]] = relationship(back_populates="customer")

    __table_args__ = (
        CheckConstraint("home_lat BETWEEN -90 AND 90", name="lat_range"),
        CheckConstraint("home_lon BETWEEN -180 AND 180", name="lon_range"),
    )


class Card(Base, TimestampMixin):
    __tablename__ = "cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    card_ref: Mapped[str] = mapped_column(String(24), unique=True, index=True)

    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), index=True
    )

    # Last four digits only. Never store a full card number — not
    # even synthetic ones, so the habit stays correct.
    last_four: Mapped[str] = mapped_column(String(4), nullable=False)
    card_type: Mapped[str] = mapped_column(String(16), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    credit_limit: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)

    customer: Mapped[Customer] = relationship(back_populates="cards")


class Merchant(Base, TimestampMixin):
    __tablename__ = "merchants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    merchant_ref: Mapped[str] = mapped_column(String(24), unique=True, index=True)

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    # MCC = Merchant Category Code, the industry standard for
    # "what kind of shop is this". One of the strongest fraud signals.
    mcc: Mapped[str] = mapped_column(String(4), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    city: Mapped[str] = mapped_column(String(80), nullable=False)
    country: Mapped[str] = mapped_column(String(2), nullable=False)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)

    # Baseline risk for this merchant, 0..1 (generator ground truth)
    risk_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    is_online: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (
        CheckConstraint("risk_score BETWEEN 0 AND 1", name="risk_range"),
    )


class Device(Base, TimestampMixin):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_ref: Mapped[str] = mapped_column(String(32), unique=True, index=True)

    device_type: Mapped[str] = mapped_column(String(24), nullable=False)
    os_family: Mapped[str] = mapped_column(String(24), nullable=True)
    # Fingerprint shared across transactions — a device seen on many
    # unrelated cards is a classic fraud-ring marker (Task 18 graph features)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


# ============================================================
#  Core event table
# ============================================================

class Transaction(Base):
    """
    One payment event. The heart of the system.

    No TimestampMixin: this table has its own event timestamp, and
    an updated_at would be meaningless — a transaction never changes.
    """

    __tablename__ = "transactions"

    # BigInteger: this table will hold millions of rows
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    transaction_ref: Mapped[str] = mapped_column(String(32), unique=True, index=True)

    # When the payment actually happened (NOT when we stored it)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    card_id: Mapped[int] = mapped_column(ForeignKey("cards.id"), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    merchant_id: Mapped[int] = mapped_column(ForeignKey("merchants.id"), index=True)
    device_id: Mapped[int | None] = mapped_column(
        ForeignKey("devices.id"), nullable=True, index=True
    )

    # Numeric, never Float, for money. Float cannot represent 0.10
    # exactly and errors compound across millions of rows.
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")

    channel: Mapped[Channel] = mapped_column(_enum(Channel, "channel"), nullable=False)
    entry_mode: Mapped[EntryMode] = mapped_column(
        _enum(EntryMode, "entry_mode"), nullable=False
    )

    # Where the transaction happened
    city: Mapped[str] = mapped_column(String(80), nullable=False)
    country: Mapped[str] = mapped_column(String(2), nullable=False)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)

    # --- Ground truth (synthetic data only) ---
    is_fraud: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, index=True
    )
    fraud_type: Mapped[FraudType] = mapped_column(
        _enum(FraudType, "fraud_type"), nullable=False, default=FraudType.NONE
    )

    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        # Composite indexes — the feature engine's most common queries.
        # "All transactions for this card, newest first" must be instant.
        Index("ix_txn_card_time", "card_id", "occurred_at"),
        Index("ix_txn_customer_time", "customer_id", "occurred_at"),
        Index("ix_txn_merchant_time", "merchant_id", "occurred_at"),
    )


# ============================================================
#  System tables
# ============================================================

class Decision(Base):
    """
    What the model said about a transaction.

    Separate from Transaction because a transaction is a FACT and a
    decision is an OPINION. Retraining produces new opinions about
    old facts; history is never rewritten.
    """

    __tablename__ = "decisions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    transaction_id: Mapped[int] = mapped_column(
        ForeignKey("transactions.id", ondelete="CASCADE"), index=True
    )

    model_version: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    action: Mapped[DecisionAction] = mapped_column(
        _enum(DecisionAction, "decision_action"), nullable=False, index=True
    )

    # Thresholds in force at decision time. Stored so an old decision
    # can still be explained after the thresholds change.
    threshold_review: Mapped[float] = mapped_column(Float, nullable=False)
    threshold_block: Mapped[float] = mapped_column(Float, nullable=False)

    # Exact feature values fed to the model — essential for debugging
    # "why did it score this?" and for detecting training/serving skew
    features: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # Top SHAP contributions, for the analyst UI
    explanation: Mapped[dict] = mapped_column(JSONB, nullable=True)

    latency_ms: Mapped[float] = mapped_column(Float, nullable=False)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    __table_args__ = (
        CheckConstraint("score BETWEEN 0 AND 1", name="score_range"),
        Index("ix_decision_model_time", "model_version", "decided_at"),
    )


class Case(Base, TimestampMixin):
    """A flagged transaction queued for human investigation."""

    __tablename__ = "cases"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    case_ref: Mapped[str] = mapped_column(String(32), unique=True, index=True)

    transaction_id: Mapped[int] = mapped_column(
        ForeignKey("transactions.id", ondelete="CASCADE"), index=True
    )
    decision_id: Mapped[int] = mapped_column(
        ForeignKey("decisions.id", ondelete="CASCADE"), index=True
    )

    status: Mapped[CaseStatus] = mapped_column(
        _enum(CaseStatus, "case_status"),
        nullable=False,
        default=CaseStatus.OPEN,
        index=True,
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    assigned_to: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # The analyst's verdict — this is the LABEL that feeds retraining (Task 30)
    verdict: Mapped[AnalystVerdict] = mapped_column(
        _enum(AnalystVerdict, "analyst_verdict"),
        nullable=False,
        default=AnalystVerdict.PENDING,
        index=True,
    )
    verdict_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint("priority BETWEEN 1 AND 5", name="priority_range"),
    )


class CaseEvent(Base):
    """
    Append-only audit trail. Rows are never updated or deleted.

    In banking this is a regulatory requirement: you must be able to
    prove who did what, when, and in what order.
    """

    __tablename__ = "case_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    case_id: Mapped[int] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), index=True
    )

    event_type: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )