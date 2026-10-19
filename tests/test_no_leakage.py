"""
Leakage tests.

Leakage is when a model sees information it would not have at
decision time. It is SILENT -- nothing crashes, and results look
better than they should. These tests are the permanent guard.

Four categories:
  1. Forbidden fields -- features must never read the label
  2. Temporal correctness -- no information from after time T
  3. State ordering -- a transaction must not affect its own features
  4. Determinism -- same input, same output
"""

from __future__ import annotations

import math

import pytest

from streamguard.features.computer import FEATURE_NAMES, FeatureComputer
from streamguard.features.state import StateStore

from .conftest import make_payload


# ============================================================
#  1. Forbidden fields
# ============================================================

class TestForbiddenFields:
    """The label must never influence a feature."""

    def test_is_fraud_does_not_change_features(self, computer):
        """
        The decisive test.

        Compute features for a transaction with is_fraud=True, then
        for the identical transaction with is_fraud=False. If any
        feature reads the label, the two results differ.
        """
        fraud_payload = make_payload(amount=5000.0, is_fraud=True,
                                     fraud_type="card_testing")
        clean_payload = make_payload(amount=5000.0, is_fraud=False,
                                     fraud_type="none")

        # Two separate computers so state cannot carry over
        features_fraud = FeatureComputer(StateStore()).compute_features(
            fraud_payload
        )
        features_clean = FeatureComputer(StateStore()).compute_features(
            clean_payload
        )

        differing = [
            name for name in FEATURE_NAMES
            if features_fraud[name] != features_clean[name]
        ]

        assert not differing, (
            f"These features changed when only the LABEL changed, which "
            f"means they read is_fraud or fraud_type: {differing}"
        )

    def test_fraud_type_does_not_change_features(self, computer):
        """Same proof for fraud_type, across all five patterns."""
        baseline = FeatureComputer(StateStore()).compute_features(
            make_payload(fraud_type="none")
        )

        for pattern in ("card_testing", "account_takeover", "geo_impossible",
                        "merchant_collusion", "card_not_present"):
            other = FeatureComputer(StateStore()).compute_features(
                make_payload(fraud_type=pattern)
            )
            differing = [
                n for n in FEATURE_NAMES if baseline[n] != other[n]
            ]
            assert not differing, (
                f"fraud_type='{pattern}' changed features: {differing}"
            )

    def test_features_survive_missing_labels(self):
        """
        Features must compute even with no label present at all.

        In production there IS no label -- that is what you are
        predicting. If the feature path needs one, it would crash the
        moment it met real traffic.
        """
        payload = make_payload()
        del payload["is_fraud"]
        del payload["fraud_type"]

        features = FeatureComputer(StateStore()).compute_features(payload)

        assert len(features) == len(FEATURE_NAMES)
        assert all(name in features for name in FEATURE_NAMES)

    def test_risk_score_not_in_payload(self):
        """
        merchants.risk_score is generator ground truth and was
        deliberately excluded from the event payload. The model must
        learn category risk from the MCC instead.
        """
        payload = make_payload()
        assert "risk_score" not in payload
        assert "merchant_risk_score" not in payload


# ============================================================
#  2. State ordering (self-leakage)
# ============================================================

class TestStateOrdering:
    """A transaction must not contribute to its own statistics."""

    def test_amount_excluded_from_own_mean(self, computer):
        """
        Ten transactions at 1,000, then one at 50,000.

        If the 50,000 leaked into its own mean, the mean would move
        to about 5,454 and the ratio would be ~9x. Correct behaviour
        keeps the mean at 1,000 and the ratio at 50x.
        """
        for i in range(10):
            computer.process(make_payload(minutes_offset=i * 10, amount=1000.0))

        features = computer.compute_features(
            make_payload(minutes_offset=200, amount=50_000.0)
        )

        assert features["amount_ratio_card_mean"] == pytest.approx(50.0, rel=1e-6)

        state = computer.store.card("CARD0000001")
        assert state.amount_stats.mean == pytest.approx(1000.0, rel=1e-9)
        assert state.amount_stats.count == 10

    def test_current_txn_not_in_velocity_count(self, computer):
        """
        Velocity counts past transactions only.

        Three earlier transactions inside the window means the fourth
        sees a count of 3, not 4.
        """
        for i in range(3):
            computer.process(make_payload(minutes_offset=i * 0.5, amount=100.0))

        features = computer.compute_features(make_payload(minutes_offset=2.0))

        assert features["txn_count_5m"] == 3

    def test_novelty_reflects_past_only(self, computer):
        """
        The first visit to a merchant must register as new, and the
        second as not-new. If update ran before compute, the first
        visit would already look familiar.
        """
        first = computer.process(
            make_payload(minutes_offset=0, merchant_ref="MERCH000777")
        )
        assert first["is_new_merchant"] == 1.0

        second = computer.process(
            make_payload(minutes_offset=10, merchant_ref="MERCH000777")
        )
        assert second["is_new_merchant"] == 0.0

    def test_compute_does_not_mutate_state(self, computer):
        """
        compute_features() must be read-only.

        Calling it twice without update_state() in between must give
        identical results and leave the state untouched.
        """
        computer.process(make_payload(minutes_offset=0, amount=500.0))

        before = computer.store.card("CARD0000001").total_count
        first = computer.compute_features(make_payload(minutes_offset=5))
        second = computer.compute_features(make_payload(minutes_offset=5))
        after = computer.store.card("CARD0000001").total_count

        assert before == after, "compute_features() modified state"
        assert first == second, "compute_features() is not pure"


# ============================================================
#  3. Temporal correctness
# ============================================================

class TestTemporalCorrectness:
    """No feature may use information from after the transaction."""

    def test_future_transactions_do_not_affect_past(self):
        """
        Process A then B. Now process A alone in a fresh computer.
        A's features must be identical -- B happened later and cannot
        have influenced it.
        """
        pair = FeatureComputer(StateStore())
        features_a_with_b = pair.process(make_payload(minutes_offset=0, amount=1000.0))
        pair.process(make_payload(minutes_offset=60, amount=99_000.0))

        alone = FeatureComputer(StateStore())
        features_a_alone = alone.process(make_payload(minutes_offset=0, amount=1000.0))

        assert features_a_with_b == features_a_alone

    def test_first_transaction_defaults(self, computer):
        """
        With no history, every history-dependent feature must return
        a defined default -- and is_first_transaction must flag it,
        so the model can tell "zero because nothing happened" from
        "zero because we do not know".
        """
        features = computer.compute_features(make_payload())

        assert features["is_first_transaction"] == 1.0
        assert features["card_txn_count"] == 0.0
        assert features["amount_zscore_card"] == 0.0
        assert features["txn_count_5m"] == 0
        assert features["distance_from_prev_km"] == 0.0
        assert features["seconds_since_prev"] == -1.0
        assert features["is_new_merchant"] == 1.0

    def test_window_boundaries(self, computer):
        """
        A transaction exactly at the window edge must be counted, and
        one just outside must not.
        """
        computer.process(make_payload(minutes_offset=0.0))      # 5m before
        computer.process(make_payload(minutes_offset=4.0))      # 1m before

        features = computer.compute_features(make_payload(minutes_offset=5.0))

        assert features["txn_count_1m"] == 1      # only the 4-minute one
        assert features["txn_count_5m"] == 2      # both


# ============================================================
#  4. Determinism and numerical safety
# ============================================================

class TestDeterminism:
    """Same input must always give the same output."""

    def test_identical_sequences_give_identical_features(self):
        """
        Two computers fed the same events must agree exactly.
        Any divergence means hidden state -- a dict iteration order,
        an unseeded random draw, a clock read.
        """
        payloads = [
            make_payload(minutes_offset=i * 3, amount=500.0 + i * 100)
            for i in range(20)
        ]

        a = FeatureComputer(StateStore())
        b = FeatureComputer(StateStore())

        for payload in payloads:
            assert a.process(payload) == b.process(payload)

    def test_no_nan_or_infinity(self, computer):
        """
        NaN and infinity break model training silently.

        This feeds deliberately awkward cases: identical timestamps,
        a huge jump in distance, a zero-variance history.
        """
        awkward = [
            make_payload(minutes_offset=0, amount=0.01),
            make_payload(minutes_offset=0, amount=500_000.0),   # same timestamp
            make_payload(minutes_offset=0.001, amount=1.0,
                         lat=25.2048, lon=55.2708, city="Dubai", country="AE"),
            make_payload(minutes_offset=10_000, amount=1000.0, device_ref=None),
        ]

        for payload in awkward:
            features = computer.process(payload)
            for name, value in features.items():
                assert not math.isnan(value), f"{name} is NaN"
                assert not math.isinf(value), f"{name} is infinity"

    def test_feature_vector_order_is_stable(self, computer):
        """
        The model learns that column 7 means a specific feature. If
        ordering ever changes between training and scoring, every
        prediction is garbage and nothing errors.
        """
        features = computer.process(make_payload())
        vector = FeatureComputer.feature_vector(features)

        assert len(vector) == len(FEATURE_NAMES)
        for i, name in enumerate(FEATURE_NAMES):
            assert vector[i] == features[name], (
                f"position {i} should be {name}"
            )