"""
Shared fixtures for the StreamGuard test suite.

pytest discovers this file automatically. Anything defined here with
@pytest.fixture can be requested by any test simply by naming it as
a function argument.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from streamguard.config.settings import settings
from streamguard.features.computer import FeatureComputer
from streamguard.features.state import StateStore

IST = timezone(timedelta(hours=5, minutes=30))
BASE_TIME = datetime(2026, 3, 1, 14, 0, 0, tzinfo=IST)


def make_payload(
    minutes_offset: float = 0.0,
    amount: float = 1000.0,
    card_ref: str = "CARD0000001",
    customer_ref: str = "CUST000001",
    merchant_ref: str = "MERCH000001",
    mcc: str = "5411",
    city: str = "Mumbai",
    lat: float = 19.0760,
    lon: float = 72.8777,
    country: str = "IN",
    channel: str = "pos",
    entry_mode: str = "chip",
    device_ref: str | None = "DEV0000001",
    is_fraud: bool = False,
    fraud_type: str = "none",
) -> dict:
    """
    Build a transaction payload shaped exactly like a real event.

    Every field has a default, so a test overrides only what it cares
    about. That keeps each test focused on one behaviour.
    """
    occurred = BASE_TIME + timedelta(minutes=minutes_offset)
    return {
        "transaction_ref": f"TXN{abs(minutes_offset):08.2f}",
        "occurred_at": occurred.isoformat(),
        "card_ref": card_ref,
        "card_type": "credit",
        "customer_ref": customer_ref,
        "merchant_ref": merchant_ref,
        "device_ref": device_ref,
        "device_type": "android_phone",
        "amount": amount,
        "currency": "INR",
        "channel": channel,
        "entry_mode": entry_mode,
        "city": city,
        "country": country,
        "lat": lat,
        "lon": lon,
        "home_city": "Mumbai",
        "home_country": "IN",
        "home_lat": 19.0760,
        "home_lon": 72.8777,
        "mcc": mcc,
        "merchant_category": "Grocery & Supermarket",
        "merchant_is_online": False,
        "merchant_city": city,
        "merchant_country": country,
        # Labels. Present in the payload by design (Task 8), but the
        # feature path must never read them.
        "is_fraud": is_fraud,
        "fraud_type": fraud_type,
    }


@pytest.fixture
def payload_factory():
    """Hand tests the payload builder."""
    return make_payload


@pytest.fixture
def computer() -> FeatureComputer:
    """A fresh FeatureComputer with empty state for each test."""
    return FeatureComputer(StateStore())


@pytest.fixture
def feature_file() -> Path:
    """
    Path to the built feature file.

    Tests that need it skip themselves if it is missing, so the suite
    still runs on a machine where features have not been built.
    """
    path = settings.processed_data_path / "features.parquet"
    if not path.exists():
        pytest.skip(f"feature file not built: {path}")
    return path