"""
src/streamguard/api/schemas.py

Task 19 - what a scoring request and response look like.

Pydantic validates incoming JSON before any of our code runs. A bad
request fails here with a clear 422, not three layers down with a
KeyError.

THE SECURITY RULE: this schema REJECTS is_fraud and fraud_type. The
event payload carries both (a deliberate, documented choice from Task
8), so a client could send them. A client sending the answer is either
confused or probing, and accepting the field would be the first step
toward a scoring path that reads it.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator, ConfigDict


FORBIDDEN_FIELDS = {"is_fraud", "fraud_type", "label", "y", "risk_score"}


class ScoreRequest(BaseModel):
    """One transaction to score.

    Field names match the event payload from Task 8 exactly, so the
    same dict that flows through the stream can be posted here. That
    is deliberate: ONE payload shape for training and serving is how
    training/serving skew is avoided.
    """

    # extra="forbid" is what rejects unknown fields, including the
    # labels. Without it, Pydantic would silently drop them and the
    # protection would be a comment rather than a rule.
    model_config = ConfigDict(extra="forbid")

    transaction_ref: str = Field(..., min_length=1, max_length=64)
    occurred_at: datetime
    card_ref: str = Field(..., min_length=1, max_length=64)
    customer_ref: str = Field(..., min_length=1, max_length=64)
    merchant_ref: str = Field(..., min_length=1, max_length=64)
    amount: float = Field(..., gt=0, le=10_000_000)
    currency: str = Field(default="INR", max_length=3)
    channel: str = Field(..., max_length=32)
    entry_mode: str = Field(..., max_length=32)

    # Optional - a card-present POS transaction has no device.
    device_ref: str | None = Field(default=None, max_length=64)
    device_type: str | None = Field(default=None, max_length=32)
    card_type: str | None = Field(default=None, max_length=32)

    # Location of the transaction.
    city: str | None = None
    country: str | None = Field(default=None, max_length=2)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)

    # The customer's home, needed for distance_from_home_km.
    home_city: str | None = None
    home_country: str | None = Field(default=None, max_length=2)
    home_lat: float | None = Field(default=None, ge=-90, le=90)
    home_lon: float | None = Field(default=None, ge=-180, le=180)

    # Merchant context.
    mcc: str | None = Field(default=None, max_length=8)
    merchant_category: str | None = None
    merchant_is_online: bool | None = None
    merchant_city: str | None = None
    merchant_country: str | None = Field(default=None, max_length=2)

    @field_validator("amount")
    @classmethod
    def amount_is_finite(cls, v: float) -> float:
        if v != v or v in (float("inf"), float("-inf")):
            raise ValueError("amount must be a finite number")
        return v

    def to_payload(self) -> dict:
        """The dict shape FeatureComputer.process() expects."""
        d = self.model_dump()
        d["occurred_at"] = self.occurred_at.isoformat()
        return d


class Contribution(BaseModel):
    """One feature's contribution to this score."""
    feature: str
    value: float
    shap: float


class ScoreResponse(BaseModel):
    """The scoring result.

    `probability` is a REAL probability: Task 14.1 removed is_unbalance
    and Task 15 measured ECE at 0.00053, so 0.30 means roughly a 30%
    chance. That is what lets `decision` come from a cost threshold
    rather than a guess.
    """
    transaction_ref: str
    probability: float
    decision: str              # approve | review | block
    threshold_used: float
    model_version: str
    n_features: int
    latency_ms: float
    top_reasons: list[Contribution] = []
    explained: bool = False
    duplicate: bool = False
    decision_source: str = "model"
    model_decision: str = ""
    overridden: bool = False
    rules_fired: list = []
    decision_explanation: str = ""

class HealthResponse(BaseModel):
    """Is the service ready to score?"""
    status: str
    model_version: str
    n_features: int
    cards_in_state: int
    merchants_in_state: int
    warmed_from: str
    warm_events: int
    warm_seconds: float
    uptime_seconds: float
    scored: int
    duplicates_rejected: int = 0
    decision_engine: dict = {}