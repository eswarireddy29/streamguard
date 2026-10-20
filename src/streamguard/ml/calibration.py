"""
src/streamguard/ml/calibration.py

Task 15.1 - is a predicted probability of 0.30 actually 30% fraud?

Ranking metrics (PR-AUC, precision@k) only care about ORDER. Task 16
computes cost-based thresholds from the probability VALUES:
    expected cost of approving = P(fraud) x 5000
    expected cost of blocking  = (1 - P(fraud)) x 200
If the probabilities are wrong, the threshold is wrong - even when the
ranking is perfect.

Task 14.1 removed is_unbalance, which should mean calibrated output.
This module checks that rather than assuming it.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd
from sklearn.calibration import calibration_curve
from sklearn.metrics import brier_score_loss


@dataclass
class CalibrationResult:
    """How well predicted probabilities match observed frequencies."""
    n: int
    n_positive: int
    prevalence: float
    mean_predicted: float
    brier: float
    brier_baseline: float
    ece: float
    max_bucket_error: float
    n_buckets_used: int
    bins: list

    def to_dict(self) -> dict:
        return asdict(self)


def reliability(y_true: np.ndarray, scores: np.ndarray,
                n_bins: int = 10, strategy: str = "quantile"
                ) -> pd.DataFrame:
    """Bucket predictions and compare predicted vs actual per bucket.

    'quantile' puts an equal NUMBER of rows in each bucket. At 0.4%
    prevalence, equal-WIDTH buckets would put 99% of rows in the first
    one and leave the rest nearly empty.
    """
    y = np.asarray(y_true).astype(int)
    s = np.asarray(scores, dtype=float)

    if strategy == "quantile":
        edges = np.unique(np.quantile(s, np.linspace(0, 1, n_bins + 1)))
    else:
        edges = np.linspace(s.min(), s.max(), n_bins + 1)

    if len(edges) < 2:
        return pd.DataFrame()

    idx = np.clip(np.digitize(s, edges[1:-1], right=False), 0, len(edges) - 2)

    rows = []
    for b in range(len(edges) - 1):
        m = idx == b
        n = int(m.sum())
        if n == 0:
            continue
        rows.append({
            "bucket": b,
            "lo": float(edges[b]),
            "hi": float(edges[b + 1]),
            "n": n,
            "mean_predicted": float(s[m].mean()),
            "actual_rate": float(y[m].mean()),
            "n_fraud": int(y[m].sum()),
        })

    df = pd.DataFrame(rows)
    if len(df):
        df["error"] = df["mean_predicted"] - df["actual_rate"]
    return df


def evaluate_calibration(y_true: np.ndarray, scores: np.ndarray,
                         n_bins: int = 10) -> CalibrationResult:
    """Brier score, ECE and the per-bucket table.

    brier_baseline is what you would score by predicting the base rate
    for every row. At 0.4% prevalence the Brier score of ANY model is
    tiny, so the baseline is the only way to read it.
    """
    y = np.asarray(y_true).astype(int)
    s = np.asarray(scores, dtype=float)

    prevalence = float(y.mean()) if len(y) else 0.0
    brier = float(brier_score_loss(y, np.clip(s, 0, 1)))
    brier_base = float(brier_score_loss(y, np.full_like(s, prevalence)))

    bins = reliability(y, s, n_bins=n_bins)

    if len(bins):
        weights = bins["n"] / bins["n"].sum()
        ece = float((weights * bins["error"].abs()).sum())
        max_err = float(bins["error"].abs().max())
    else:
        ece, max_err = float("nan"), float("nan")

    return CalibrationResult(
        n=len(y),
        n_positive=int(y.sum()),
        prevalence=prevalence,
        mean_predicted=float(s.mean()),
        brier=brier,
        brier_baseline=brier_base,
        ece=ece,
        max_bucket_error=max_err,
        n_buckets_used=len(bins),
        bins=bins.to_dict(orient="records") if len(bins) else [],
    )


def format_calibration(r: CalibrationResult) -> str:
    """Terminal report. ASCII only."""
    out = []
    out.append(f"  rows {r.n:,}   fraud {r.n_positive:,}   "
               f"prevalence {r.prevalence * 100:.3f}%")
    out.append(f"  mean predicted probability  {r.mean_predicted:.5f}")
    out.append(f"  actual fraud rate           {r.prevalence:.5f}")
    bias = r.mean_predicted - r.prevalence
    out.append(f"  bias (predicted - actual)   {bias:+.5f}")
    out.append("")
    out.append(f"  Brier score      {r.brier:.6f}")
    out.append(f"  Brier baseline   {r.brier_baseline:.6f}  "
               f"(predicting the base rate for every row)")
    if r.brier_baseline:
        out.append(f"  improvement      {(1 - r.brier / r.brier_baseline) * 100:.1f}%")
    out.append("")
    out.append(f"  ECE              {r.ece:.5f}  "
               "(weighted mean gap between predicted and actual)")
    out.append(f"  worst bucket     {r.max_bucket_error:.5f}")
    out.append("")
    out.append("  reliability by bucket (equal row counts):")
    out.append(f"    {'bucket':<8}{'n':>9}{'predicted':>12}"
               f"{'actual':>10}{'fraud':>8}{'error':>10}")
    out.append("    " + "-" * 57)
    for b in r.bins:
        out.append(f"    {b['bucket']:<8}{b['n']:>9,}"
                   f"{b['mean_predicted']:>12.5f}{b['actual_rate']:>10.5f}"
                   f"{b['n_fraud']:>8,}{b['error']:>+10.5f}")
    return "\n".join(out)


def verdict(r: CalibrationResult) -> str:
    """Plain-English reading of the numbers."""
    lines = []
    bias = r.mean_predicted - r.prevalence

    if abs(bias) < 0.001:
        lines.append("  Overall bias is negligible - the model predicts the")
        lines.append("  right amount of fraud in total.")
    elif bias > 0:
        lines.append(f"  The model OVER-predicts fraud by {bias:.5f} on average.")
        lines.append("  Cost thresholds computed from these probabilities would")
        lines.append("  block more than they should.")
    else:
        lines.append(f"  The model UNDER-predicts fraud by {abs(bias):.5f}.")
        lines.append("  Cost thresholds would approve more than they should.")

    lines.append("")
    if r.ece < 0.005:
        lines.append("  ECE is small: probabilities are usable as probabilities.")
        lines.append("  Task 16 can compute cost thresholds directly from them.")
    elif r.ece < 0.02:
        lines.append("  ECE is moderate. Usable, but consider isotonic or")
        lines.append("  Platt calibration before the cost work in Task 16.")
    else:
        lines.append("  ECE is large: do NOT treat these as real probabilities.")
        lines.append("  Calibrate before Task 16, or the thresholds will be wrong.")
    return "\n".join(lines)