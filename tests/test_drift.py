"""
tests/test_drift.py

Task 30 - PSI and KS, verified against known answers.

Evidently was meant to be the cross-check and its 0.5.1 API did not
match, so these tests are the only thing standing between my PSI
implementation and a wrong number on a dashboard. They check it
against cases where the correct answer is known by construction.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from streamguard.ml.drift import (
    CUMULATIVE_FEATURES, PSI_MODERATE, PSI_NO_CHANGE,
    classify, feature_drift, ks_test, population_stability_index,
    prediction_drift, summarise,
)


@pytest.fixture
def rng():
    return np.random.default_rng(42)


class TestPSIKnownAnswers:
    """Cases where the right answer is known by construction."""

    def test_identical_distributions_give_zero(self, rng):
        """THE DECISIVE TEST. A distribution against itself must be 0.
        Anything else means the binning or the arithmetic is wrong."""
        x = rng.normal(0, 1, 10_000)
        assert population_stability_index(x, x) == pytest.approx(0.0, abs=1e-9)

    def test_same_distribution_different_samples_is_small(self, rng):
        """Two draws from the same distribution should look stable."""
        a = rng.normal(0, 1, 50_000)
        b = rng.normal(0, 1, 50_000)
        assert population_stability_index(a, b) < PSI_NO_CHANGE

    def test_shifted_mean_is_detected(self, rng):
        """A full standard deviation of shift must not read stable."""
        a = rng.normal(0, 1, 50_000)
        b = rng.normal(1, 1, 50_000)
        assert population_stability_index(a, b) > PSI_MODERATE

    def test_bigger_shift_gives_bigger_psi(self, rng):
        a = rng.normal(0, 1, 20_000)
        small = population_stability_index(a, rng.normal(0.3, 1, 20_000))
        large = population_stability_index(a, rng.normal(2.0, 1, 20_000))
        assert large > small

    def test_widened_variance_is_detected(self, rng):
        """Same mean, different spread. A mean-only check would miss
        this entirely, which is why PSI bins rather than comparing
        averages."""
        a = rng.normal(0, 1, 50_000)
        b = rng.normal(0, 3, 50_000)
        assert population_stability_index(a, b) > PSI_NO_CHANGE

    def test_psi_is_never_negative(self, rng):
        for _ in range(5):
            a = rng.normal(0, 1, 5_000)
            b = rng.normal(rng.uniform(-2, 2), rng.uniform(0.5, 3), 5_000)
            assert population_stability_index(a, b) >= 0


class TestPSIEdgeCases:
    def test_constant_feature_does_not_crash(self):
        a = np.full(1000, 5.0)
        assert np.isfinite(population_stability_index(a, a))

    def test_empty_input_returns_nan(self):
        assert np.isnan(population_stability_index(np.array([]),
                                                   np.array([1.0, 2.0])))

    def test_nan_values_are_ignored_not_propagated(self, rng):
        """A NaN in the data must not make the whole PSI NaN - that
        would silently disable monitoring for that feature."""
        a = rng.normal(0, 1, 5_000)
        b = np.concatenate([rng.normal(0, 1, 4_990), np.full(10, np.nan)])
        assert np.isfinite(population_stability_index(a, b))

    def test_infinity_is_ignored(self, rng):
        a = rng.normal(0, 1, 5_000)
        b = np.concatenate([rng.normal(0, 1, 4_990), np.full(10, np.inf)])
        assert np.isfinite(population_stability_index(a, b))


class TestKS:
    def test_identical_samples_give_near_zero(self, rng):
        x = rng.normal(0, 1, 5_000)
        stat, _ = ks_test(x, x)
        assert stat == pytest.approx(0.0, abs=1e-9)

    def test_shift_raises_the_statistic(self, rng):
        a = rng.normal(0, 1, 10_000)
        stat, _ = ks_test(a, rng.normal(2, 1, 10_000))
        assert stat > 0.5

    def test_statistic_is_bounded_to_one(self, rng):
        """KS is a maximum CDF gap, so it cannot exceed 1."""
        a = rng.normal(0, 1, 1_000)
        stat, _ = ks_test(a, rng.normal(100, 1, 1_000))
        assert 0 <= stat <= 1


class TestClassification:
    def test_thresholds(self):
        assert classify(0.05) == "stable"
        assert classify(0.15) == "moderate"
        assert classify(0.50) == "significant"

    def test_cumulative_features_bypass_the_thresholds(self):
        """FOUND AT TASK 30: card_age_days scored PSI 11.42 while
        being a day counter on a 90-day simulation. A monitor that
        cries wolf daily is one people stop reading."""
        assert classify(11.42, "card_age_days") == "cumulative"
        assert classify(0.001, "card_age_days") == "cumulative"

    def test_the_counters_are_all_listed(self):
        for f in ("card_age_days", "card_txn_count", "merchant_txn_count"):
            assert f in CUMULATIVE_FEATURES

    def test_a_normal_feature_is_not_exempt(self):
        assert classify(11.42, "amount") == "significant"


class TestFeatureDrift:
    def test_sorted_worst_first(self, rng):
        ref = pd.DataFrame({"a": rng.normal(0, 1, 5_000),
                            "b": rng.normal(0, 1, 5_000)})
        cur = pd.DataFrame({"a": rng.normal(0, 1, 5_000),
                            "b": rng.normal(3, 1, 5_000)})
        d = feature_drift(ref, cur, ["a", "b"])
        assert d.iloc[0]["feature"] == "b"

    def test_missing_columns_are_skipped_not_crashed(self, rng):
        ref = pd.DataFrame({"a": rng.normal(0, 1, 100)})
        cur = pd.DataFrame({"a": rng.normal(0, 1, 100)})
        d = feature_drift(ref, cur, ["a", "does_not_exist"])
        assert len(d) == 1

    def test_summary_counts_add_up(self, rng):
        ref = pd.DataFrame({f"f{i}": rng.normal(0, 1, 2_000)
                            for i in range(5)})
        cur = pd.DataFrame({f"f{i}": rng.normal(0, 1, 2_000)
                            for i in range(5)})
        s = summarise(feature_drift(ref, cur, list(ref.columns)))
        total = (s["stable"] + s["moderate"] + s["significant"]
                 + s.get("cumulative", 0))
        assert total == s["n_features"]


class TestPredictionDrift:
    def test_identical_scores_are_stable(self, rng):
        s = rng.beta(0.5, 50, 10_000)
        assert prediction_drift(s, s)["verdict"] == "stable"

    def test_flagged_rate_uses_the_task_16_threshold(self, rng):
        """The reported flagged percentage must use the cost-optimised
        threshold, not 0.5."""
        low = np.full(1_000, 0.001)
        result = prediction_drift(low, low)
        assert result["reference_flagged_pct"] == 0.0

        high = np.full(1_000, 0.9)
        assert prediction_drift(high, high)["current_flagged_pct"] == 100.0