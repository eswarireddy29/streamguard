"""
Online feature computation.

Turns one transaction event plus accumulated state into a row of
numbers a model can learn from.

THE GOVERNING RULE
------------------
A feature for the transaction at time T uses ONLY events strictly
before T. This is enforced structurally: compute_features() READS
state, update_state() WRITES it, and the caller must invoke them in
that order. They are never interleaved.

Break the rule and you get look-ahead leakage: the model sees the
future, scores beautifully in testing, and fails in production. It is
silent -- no exception, just numbers that are too good.

FORBIDDEN FIELDS
----------------
This module must NEVER read payload["is_fraud"] or
payload["fraud_type"]. They exist in the event for training and
evaluation only. A test in Task 11 enforces this.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from streamguard.features.state import (
    CardState,
    StateStore,
    TransactionMemory,
)
from streamguard.utils.geo import haversine_km, implied_speed_kmh
from streamguard.utils.logging_config import get_logger

log = get_logger(__name__)

# Windows used by the velocity features. Chosen to span the
# timescales our fraud patterns operate on: card testing bursts in
# seconds, account takeover over hours.
WINDOWS: dict[str, timedelta] = {
    "1m": timedelta(minutes=1),
    "5m": timedelta(minutes=5),
    "1h": timedelta(hours=1),
    "24h": timedelta(hours=24),
}

# Above this, the cardholder would have to be on a commercial
# aircraft. Above ~1200 it is physically impossible.
IMPLAUSIBLE_SPEED_KMH = 900.0

# Hours counted as "night" for the is_night flag, in LOCAL time.
NIGHT_HOURS = {23, 0, 1, 2, 3, 4, 5}


# The complete feature list, in a fixed order. Order matters: the
# model expects columns in the same sequence at training and at
# scoring time. A mismatch is silent and catastrophic.
FEATURE_NAMES: list[str] = [
    # --- Amount (8) ---
    "amount",
    "amount_log",
    "amount_zscore_card",
    "amount_ratio_card_mean",
    "amount_ratio_card_ema",
    "amount_ratio_card_max",
    "amount_zscore_customer",
    "amount_vs_merchant_mean",
    # --- Velocity (10) ---
    "txn_count_1m",
    "txn_count_5m",
    "txn_count_1h",
    "txn_count_24h",
    "amount_sum_1h",
    "amount_sum_24h",
    "distinct_merchants_1h",
    "distinct_mccs_1h",
    "distinct_cities_24h",
    "velocity_ratio_5m_24h",
    # --- Geography (6) ---
    "distance_from_prev_km",
    "implied_speed_kmh",
    "is_speed_implausible",
    "distance_from_home_km",
    "is_foreign_country",
    "distinct_countries_24h",
    # --- Novelty (8) ---
    "is_new_merchant",
    "is_new_mcc",
    "is_new_city",
    "is_new_device",
    "is_new_country",
    "card_distinct_merchants",
    "card_distinct_mccs",
    "merchant_novelty_rate",
    # --- Temporal (7) ---
    "hour_of_day",
    "day_of_week",
    "is_weekend",
    "is_night",
    "seconds_since_prev",
    "card_age_days",
    "card_txn_count",
    # --- Merchant (6) ---
    "merchant_txn_count",
    "merchant_amount_mean",
    "merchant_amount_std",
    "merchant_distinct_cards",
    "merchant_amount_zscore",
    "merchant_is_online",
    # --- Context flags (4) ---
    "is_first_transaction",
    "is_ecommerce",
    "is_manual_entry",
    "is_card_present",
]


class FeatureComputer:
    """
    Computes features from event + state.

    Stateless itself -- all state lives in the StateStore passed in.
    That separation makes the computer trivially testable: feed it a
    known state and a known event, assert on the output.
    """

    def __init__(self, store: StateStore | None = None):
        self.store = store or StateStore()

    # ============================================================
    #  PHASE 1 — READ state, compute features
    # ============================================================

    def compute_features(self, payload: dict[str, Any]) -> dict[str, float]:
        """
        Build the feature row for one transaction.

        Reads state only. Does NOT modify it. The caller must call
        update_state() afterwards.
        """
        card_ref = payload["card_ref"]
        customer_ref = payload["customer_ref"]
        merchant_ref = payload["merchant_ref"]

        occurred_at = payload["occurred_at"]
        if isinstance(occurred_at, str):
            occurred_at = datetime.fromisoformat(occurred_at)

        amount = float(payload["amount"])

        card = self.store.card(card_ref)
        customer = self.store.customer(customer_ref)
        merchant = self.store.merchant(merchant_ref)

        features: dict[str, float] = {}

        features.update(self._amount_features(
            payload, card, customer, merchant, amount
        ))
        features.update(self._velocity_features(card, occurred_at))
        features.update(self._geo_features(payload, card, occurred_at))
        features.update(self._novelty_features(payload, card))
        features.update(self._temporal_features(payload, card, occurred_at))
        features.update(self._merchant_features(payload, merchant, amount))
        features.update(self._context_features(payload, card))

        return features

    # ---------- Amount ----------

    def _amount_features(self, payload, card, customer, merchant,
                         amount: float) -> dict[str, float]:
        import math

        return {
            "amount": amount,
            # log1p compresses the huge dynamic range (Rs 1 to
            # Rs 500,000) so the model is not dominated by scale.
            # log1p rather than log because log(0) is undefined.
            "amount_log": math.log1p(amount),

            # How unusual is this amount FOR THIS CARD? Returns 0.0
            # when there is no history -- see RunningStats.z_score.
            "amount_zscore_card": card.amount_stats.z_score(amount),
            "amount_ratio_card_mean": card.amount_stats.ratio_to_mean(amount),

            # EMA reacts faster than the full-history mean, so a
            # genuine shift in spending shows up sooner.
            "amount_ratio_card_ema": card.amount_ema.ratio(amount),

            # Ratio to the largest amount ever seen on this card.
            # Above 1.0 means a new record -- a strong signal.
            "amount_ratio_card_max": (
                amount / card.amount_stats.maximum
                if card.amount_stats.count > 0
                and card.amount_stats.maximum > 0
                else 1.0
            ),

            # Across all of this customer's cards
            "amount_zscore_customer": customer.amount_stats.z_score(amount),

            # Against this merchant's typical ticket size
            "amount_vs_merchant_mean": merchant.amount_stats.ratio_to_mean(amount),
        }

    # ---------- Velocity ----------

    def _velocity_features(self, card: CardState,
                           now: datetime) -> dict[str, float]:
        count_5m = card.count_within(now, WINDOWS["5m"])
        count_24h = card.count_within(now, WINDOWS["24h"])

        return {
            "txn_count_1m": card.count_within(now, WINDOWS["1m"]),
            "txn_count_5m": count_5m,
            "txn_count_1h": card.count_within(now, WINDOWS["1h"]),
            "txn_count_24h": count_24h,

            "amount_sum_1h": card.sum_within(now, WINDOWS["1h"]),
            "amount_sum_24h": card.sum_within(now, WINDOWS["24h"]),

            "distinct_merchants_1h": card.distinct_within(
                now, WINDOWS["1h"], "merchant_ref"
            ),
            "distinct_mccs_1h": card.distinct_within(
                now, WINDOWS["1h"], "mcc"
            ),
            "distinct_cities_24h": card.distinct_within(
                now, WINDOWS["24h"], "city"
            ),

            # Burstiness: what fraction of a day's activity happened
            # in the last five minutes? Near 1.0 means everything just
            # happened at once -- the card-testing signature.
            "velocity_ratio_5m_24h": (
                count_5m / count_24h if count_24h > 0 else 0.0
            ),
        }

    # ---------- Geography ----------

    def _geo_features(self, payload, card: CardState,
                      now: datetime) -> dict[str, float]:
        lat = float(payload["lat"])
        lon = float(payload["lon"])
        country = payload["country"]

        previous = card.previous

        if previous is None:
            distance = 0.0
            speed = 0.0
            implausible = 0.0
        else:
            distance = haversine_km(previous.lat, previous.lon, lat, lon)
            seconds = (now - previous.occurred_at).total_seconds()
            speed = implied_speed_kmh(distance, seconds)
            # Guard against infinity: two transactions at the exact
            # same timestamp give infinite speed, which would break
            # the model. Cap at a large finite number instead.
            if speed == float("inf"):
                speed = 99_999.0
            implausible = 1.0 if speed > IMPLAUSIBLE_SPEED_KMH else 0.0

        home_distance = haversine_km(
            float(payload["home_lat"]), float(payload["home_lon"]), lat, lon
        )

        return {
            "distance_from_prev_km": distance,
            "implied_speed_kmh": min(speed, 99_999.0),
            "is_speed_implausible": implausible,
            "distance_from_home_km": home_distance,
            "is_foreign_country": 0.0 if country == payload["home_country"] else 1.0,
            "distinct_countries_24h": len(card.seen_countries),
        }

    # ---------- Novelty ----------

    def _novelty_features(self, payload, card: CardState) -> dict[str, float]:
        merchant_ref = payload["merchant_ref"]
        mcc = payload["mcc"]
        city = payload["city"]
        device_ref = payload.get("device_ref")
        country = payload["country"]

        return {
            # "Have I seen this before on this card?" -- the core
            # account-takeover signal. An attacker shops where the
            # victim does not.
            "is_new_merchant": 0.0 if merchant_ref in card.seen_merchants else 1.0,
            "is_new_mcc": 0.0 if mcc in card.seen_mccs else 1.0,
            "is_new_city": 0.0 if city in card.seen_cities else 1.0,
            "is_new_device": (
                0.0 if (device_ref and device_ref in card.seen_devices) else 1.0
            ),
            "is_new_country": 0.0 if country in card.seen_countries else 1.0,

            "card_distinct_merchants": len(card.seen_merchants),
            "card_distinct_mccs": len(card.seen_mccs),

            # How exploratory is this card normally? A card that
            # always visits new merchants makes "new merchant" weak
            # evidence; a card that never does makes it strong.
            "merchant_novelty_rate": (
                len(card.seen_merchants) / card.total_count
                if card.total_count > 0 else 0.0
            ),
        }

    # ---------- Temporal ----------

    def _temporal_features(self, payload, card: CardState,
                           now: datetime) -> dict[str, float]:
        # now carries +05:30, so .hour and .weekday() are already
        # LOCAL time. This is why the Task 6 timezone fix mattered:
        # with UTC timestamps, is_night would have been wrong by
        # five and a half hours for every single row.
        hour = now.hour
        weekday = now.weekday()

        previous = card.previous
        seconds_since = (
            (now - previous.occurred_at).total_seconds()
            if previous is not None else -1.0
        )

        return {
            "hour_of_day": float(hour),
            "day_of_week": float(weekday),
            "is_weekend": 1.0 if weekday >= 5 else 0.0,
            "is_night": 1.0 if hour in NIGHT_HOURS else 0.0,
            # -1 means "no previous transaction", distinguishable
            # from 0 meaning "simultaneous"
            "seconds_since_prev": seconds_since,
            "card_age_days": card.age_days(now),
            "card_txn_count": float(card.total_count),
        }

    # ---------- Merchant ----------

    def _merchant_features(self, payload, merchant,
                           amount: float) -> dict[str, float]:
        return {
            "merchant_txn_count": float(merchant.total_count),
            "merchant_amount_mean": merchant.amount_stats.mean,
            "merchant_amount_std": merchant.amount_stats.std,
            "merchant_distinct_cards": float(len(merchant.distinct_cards)),
            # Collusion inflates amounts at ONE merchant. Per
            # transaction it looks ordinary; against the merchant's
            # own distribution it stands out.
            "merchant_amount_zscore": merchant.amount_stats.z_score(amount),
            "merchant_is_online": 1.0 if payload.get("merchant_is_online") else 0.0,
        }

    # ---------- Context ----------

    def _context_features(self, payload, card: CardState) -> dict[str, float]:
        channel = payload.get("channel", "")
        entry_mode = payload.get("entry_mode", "")

        return {
            # Lets the model distinguish "0 because nothing happened"
            # from "0 because we have no history"
            "is_first_transaction": 1.0 if card.total_count == 0 else 0.0,
            "is_ecommerce": 1.0 if channel in ("ecommerce", "recurring") else 0.0,
            "is_manual_entry": 1.0 if entry_mode == "manual" else 0.0,
            "is_card_present": 1.0 if entry_mode in ("chip", "swipe", "nfc") else 0.0,
        }

    # ============================================================
    #  PHASE 2 — WRITE state
    # ============================================================

    def update_state(self, payload: dict[str, Any]) -> None:
        """
        Fold this transaction into the state.

        MUST be called AFTER compute_features(). Calling it first
        would let the transaction contribute to its own statistics.
        """
        occurred_at = payload["occurred_at"]
        if isinstance(occurred_at, str):
            occurred_at = datetime.fromisoformat(occurred_at)

        amount = float(payload["amount"])
        card_ref = payload["card_ref"]
        merchant_ref = payload["merchant_ref"]

        memory = TransactionMemory(
            occurred_at=occurred_at,
            amount=amount,
            lat=float(payload["lat"]),
            lon=float(payload["lon"]),
            merchant_ref=merchant_ref,
            mcc=payload["mcc"],
            city=payload["city"],
            channel=payload.get("channel", ""),
        )

        self.store.card(card_ref).update(
            memory,
            device_ref=payload.get("device_ref"),
            country=payload["country"],
        )
        self.store.merchant(merchant_ref).update(amount, card_ref)
        self.store.customer(payload["customer_ref"]).update(amount, card_ref)

    # ============================================================
    #  Convenience
    # ============================================================

    def process(self, payload: dict[str, Any]) -> dict[str, float]:
        """
        Compute features then update state, in the correct order.

        Use this rather than calling the two phases by hand -- it is
        the only place the ordering is encoded, so it cannot be got
        wrong elsewhere.
        """
        features = self.compute_features(payload)
        self.update_state(payload)
        return features

    @staticmethod
    def feature_vector(features: dict[str, float]) -> list[float]:
        """
        Convert the feature dict to a list in FEATURE_NAMES order.

        Column order must be identical at training and scoring time.
        Relying on dict insertion order would work today and break
        silently the day someone reorders a method.
        """
        return [float(features.get(name, 0.0)) for name in FEATURE_NAMES]