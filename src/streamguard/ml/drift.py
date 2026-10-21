"""
src/streamguard/ml/drift.py

Task 30 - has the world changed since the model was trained?

A model is trained on a snapshot. Spending patterns shift, fraudsters
adapt, a new merchant category appears. The model keeps returning
confident scores the whole time, because nothing in it knows the
inputs have moved. Drift detection is how you find out before the
recall quietly collapses.

TWO MEASURES, deliberately, because they catch different things:

  PSI (Population Stability Index) measures how much PROBABILITY MASS
  moved between bins. It is the banking industry standard, the
  thresholds below are the conventional ones, and it is a formula you
  can write on a whiteboard.

  KS (Kolmogorov-Smirnov) measures the largest gap between two
  cumulative distributions. It is sensitive to a shift in the MIDDLE
  of a distribution that PSI's binning can smooth away.

Both are computed here rather than taken from a library, because a
number you cannot explain is a number you cannot defend. Evidently
runs over the same data in scripts/check_drift.py as a cross-check.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd
from scipy import stats


# The conventional banking thresholds. They are rules of thumb, not
# laws - stated explicitly so they can be argued with.
PSI_NO_CHANGE = 0.10      # below this, treat as stable
PSI_MODERATE = 0.25       # between: investigate
                          # above: the population has materially moved


@dataclass
class FeatureDrift:
    """Drift for one feature."""
    feature: str
    psi: float
    ks_statistic: float
    ks_pvalue: float
    reference_mean: float
    current_mean: float
    mean_shift_pct: float
    verdict: str
    n_reference: int
    n_current: int

    def to_dict(self) -> dict:
        return asdict(self)


def population_stability_index(reference: np.ndarray, current: np.ndarray,
                               bins: int = 10) -> float:
    """PSI = sum over bins of (current% - reference%) * ln(current% / reference%)

    Read it as: for each bin, how much mass moved, weighted by how
    surprising that move is. A bin that doubles contributes more than
    one that grows 10%.

    Bin edges come from the REFERENCE distribution, not the combined
    data. Using combined edges would let the current period define the
    bins it is being judged against, which hides exactly the shift
    being looked for.

    Empty bins are floored at a small epsilon: ln(0) is undefined and
    a bin that was empty and is now full is real drift, not an error.
    """
    ref = np.asarray(reference, dtype=float)
    cur = np.asarray(current, dtype=float)
    ref = ref[np.isfinite(ref)]
    cur = cur[np.isfinite(cur)]

    if len(ref) == 0 or len(cur) == 0:
        return float("nan")

    # Quantile edges from the reference. A constant feature collapses
    # to one bin, which correctly reports zero drift.
    edges = np.unique(np.quantile(ref, np.linspace(0, 1, bins + 1)))
    if len(edges) < 2:
        return 0.0 if np.array_equal(np.unique(cur), np.unique(ref)) else 1.0

    edges[0], edges[-1] = -np.inf, np.inf

    ref_counts, _ = np.histogram(ref, bins=edges)
    cur_counts, _ = np.histogram(cur, bins=edges)

    eps = 1e-6
    ref_pct = np.maximum(ref_counts / len(ref), eps)
    cur_pct = np.maximum(cur_counts / len(cur), eps)

    return float(np.sum((cur_pct - ref_pct) * np.log(cur_pct / ref_pct)))


def ks_test(reference: np.ndarray, current: np.ndarray) -> tuple:
    """Kolmogorov-Smirnov: the largest vertical gap between two CDFs.

    The p-value is reported but should be read carefully: with
    hundreds of thousands of rows, a trivially small shift becomes
    "significant". The STATISTIC (the gap itself) is the number worth
    acting on.
    """
    ref = np.asarray(reference, dtype=float)
    cur = np.asarray(current, dtype=float)
    ref = ref[np.isfinite(ref)]
    cur = cur[np.isfinite(cur)]

    if len(ref) < 2 or len(cur) < 2:
        return float("nan"), float("nan")

    result = stats.ks_2samp(ref, cur)
    return float(result.statistic), float(result.pvalue)

# Features that are cumulative counters, not distributions. They grow
# monotonically for the life of the simulation, so PSI reports
# "significant drift" every single day, forever.
#
# FOUND AT TASK 30: card_age_days scored PSI 11.42 (threshold 0.25)
# with its mean moving 30.5 -> 82.1. That is not drift - the
# simulation is 90 days long and the counter counts days.
#
# A monitor that cries wolf daily is one people stop reading, and
# real drift would be invisible underneath. These are reported
# separately rather than suppressed: the growth itself is worth
# watching, just not against a distribution threshold.
CUMULATIVE_FEATURES = {
    "card_age_days",
    "card_txn_count",
    "card_distinct_merchants",
    "card_distinct_mccs",
    "merchant_txn_count",
    "merchant_distinct_cards",
    "merchant_novelty_rate",
}


def classify(psi: float, feature: str | None = None) -> str:
    if feature in CUMULATIVE_FEATURES:
        return "cumulative"
    if not np.isfinite(psi):
        return "unknown"
    if psi < PSI_NO_CHANGE:
        return "stable"
    if psi < PSI_MODERATE:
        return "moderate"
    return "significant"


def feature_drift(reference: pd.DataFrame, current: pd.DataFrame,
                  features: list, bins: int = 10) -> pd.DataFrame:
    """Drift for every feature, worst first."""
    rows = []
    for f in features:
        if f not in reference.columns or f not in current.columns:
            continue
        ref = reference[f].to_numpy(dtype=float)
        cur = current[f].to_numpy(dtype=float)

        psi = population_stability_index(ref, cur, bins=bins)
        ks_stat, ks_p = ks_test(ref, cur)

        ref_mean = float(np.nanmean(ref)) if len(ref) else float("nan")
        cur_mean = float(np.nanmean(cur)) if len(cur) else float("nan")
        shift = (100 * (cur_mean - ref_mean) / ref_mean
                 if ref_mean not in (0, float("nan")) else float("nan"))

        rows.append(FeatureDrift(
            feature=f, psi=psi, ks_statistic=ks_stat, ks_pvalue=ks_p,
            reference_mean=ref_mean, current_mean=cur_mean,
            mean_shift_pct=shift, verdict=classify(psi, f),
            n_reference=len(ref), n_current=len(cur),
        ).to_dict())

    return (pd.DataFrame(rows)
            .sort_values("psi", ascending=False)
            .reset_index(drop=True))


def prediction_drift(reference_scores: np.ndarray,
                     current_scores: np.ndarray) -> dict:
    """Drift in the model's OUTPUT, not its inputs.

    This is the most useful single signal. Input drift might be
    harmless - a feature can move without changing what the model
    concludes. Output drift means the model's behaviour has changed,
    whatever the cause, and that is what reaches a customer.
    """
    psi = population_stability_index(reference_scores, current_scores)
    ks_stat, ks_p = ks_test(reference_scores, current_scores)

    ref = np.asarray(reference_scores, dtype=float)
    cur = np.asarray(current_scores, dtype=float)

    return {
        "psi": psi,
        "verdict": classify(psi),
        "ks_statistic": ks_stat,
        "ks_pvalue": ks_p,
        "reference_mean": float(np.nanmean(ref)),
        "current_mean": float(np.nanmean(cur)),
        "reference_flagged_pct": float(np.mean(ref >= 0.03061) * 100),
        "current_flagged_pct": float(np.mean(cur >= 0.03061) * 100),
    }


def summarise(drift: pd.DataFrame) -> dict:
    """One line a dashboard can show."""
    if len(drift) == 0:
        return {"status": "no features compared"}
    counts = drift["verdict"].value_counts().to_dict()
    # The worst DISTRIBUTIONAL drift, excluding counters.
    real = drift[drift["verdict"] != "cumulative"]
    worst = real.iloc[0] if len(real) else drift.iloc[0]
    return {
        "n_features": len(drift),
        "stable": counts.get("stable", 0),
        "cumulative": counts.get("cumulative", 0),
        "moderate": counts.get("moderate", 0),
        "significant": counts.get("significant", 0),
        "worst_feature": worst["feature"],
        "worst_psi": float(worst["psi"]),
        "overall": ("significant" if counts.get("significant")
                    else "moderate" if counts.get("moderate")
                    else "stable"),
    }