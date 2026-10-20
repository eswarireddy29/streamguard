"""
src/streamguard/ml/costs.py

Task 16 - choose the threshold by MONEY, not by 0.5.

A threshold of 0.5 is the right answer only when a false positive and
a false negative cost the same. Here they do not:

    missed fraud (false negative)  = Rs 5,000  - the money is gone
    blocked customer (false pos.)  = Rs   200  - support call, churn risk

That 25:1 asymmetry means the optimal threshold is far below 0.5: it is
worth blocking roughly 25 legitimate transactions to catch one fraud.
The exact point is computed from the data, not guessed.

This works because Task 15 confirmed the probabilities are calibrated
(ECE 0.00053). An uncalibrated score would give a meaningless threshold.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class CostModel:
    """What each kind of mistake costs, in rupees.

    These are ASSUMPTIONS, not measured figures. A real bank would take
    them from chargeback data and churn analysis. They are stated here
    so the threshold can be defended and re-run with other numbers.
    """
    false_negative: float = 5000.0   # fraud approved - the money is lost
    false_positive: float = 200.0    # genuine customer blocked
    true_positive: float = 0.0       # fraud caught - loss avoided
    true_negative: float = 0.0       # normal approved - business as usual

    # A reviewed case costs analyst time rather than money lost.
    review: float = 50.0

    @property
    def ratio(self) -> float:
        return self.false_negative / self.false_positive


@dataclass
class ThresholdResult:
    """One threshold and what it would have cost."""
    threshold: float
    tp: int
    fp: int
    tn: int
    fn: int
    precision: float
    recall: float
    total_cost: float
    cost_per_1000: float
    flagged: int
    flag_rate: float

    def to_dict(self) -> dict:
        return asdict(self)


def confusion(y_true: np.ndarray, scores: np.ndarray,
              threshold: float) -> tuple[int, int, int, int]:
    """Counts at one threshold: tp, fp, tn, fn."""
    y = np.asarray(y_true).astype(bool)
    pred = np.asarray(scores, dtype=float) >= threshold
    tp = int((pred & y).sum())
    fp = int((pred & ~y).sum())
    tn = int((~pred & ~y).sum())
    fn = int((~pred & y).sum())
    return tp, fp, tn, fn


def cost_at(y_true: np.ndarray, scores: np.ndarray, threshold: float,
            costs: CostModel) -> ThresholdResult:
    """What this threshold would have cost on this data."""
    tp, fp, tn, fn = confusion(y_true, scores, threshold)
    n = tp + fp + tn + fn

    total = (fn * costs.false_negative + fp * costs.false_positive
             + tp * costs.true_positive + tn * costs.true_negative)

    flagged = tp + fp
    return ThresholdResult(
        threshold=float(threshold),
        tp=tp, fp=fp, tn=tn, fn=fn,
        precision=tp / flagged if flagged else 0.0,
        recall=tp / (tp + fn) if (tp + fn) else 0.0,
        total_cost=float(total),
        cost_per_1000=float(1000 * total / n) if n else 0.0,
        flagged=flagged,
        flag_rate=flagged / n if n else 0.0,
    )


def sweep(y_true: np.ndarray, scores: np.ndarray, costs: CostModel,
          n_points: int = 200) -> pd.DataFrame:
    """Cost at every candidate threshold.

    Candidates come from the score distribution itself (quantiles), not
    from an even grid: almost all scores sit near zero, so an even grid
    would waste most of its points in empty space.
    """
    s = np.asarray(scores, dtype=float)
    qs = np.quantile(s, np.linspace(0.90, 1.0, n_points))
    candidates = np.unique(np.concatenate([qs, [0.5], np.linspace(0, 0.1, 50)]))
    candidates = candidates[(candidates > 0) & (candidates < 1)]

    rows = [cost_at(y_true, s, t, costs).to_dict() for t in candidates]
    return pd.DataFrame(rows).sort_values("threshold").reset_index(drop=True)


def optimal(y_true: np.ndarray, scores: np.ndarray,
            costs: CostModel, n_points: int = 200
            ) -> tuple[ThresholdResult, pd.DataFrame]:
    """The cheapest threshold, plus the full sweep."""
    df = sweep(y_true, scores, costs, n_points)
    best_row = df.loc[df["total_cost"].idxmin()]
    best = cost_at(y_true, scores, float(best_row["threshold"]), costs)
    return best, df


def theoretical_threshold(costs: CostModel) -> float:
    """The textbook optimum for a perfectly calibrated model.

    Block when the expected cost of approving exceeds the expected cost
    of blocking:
        p * FN  >  (1 - p) * FP
        p       >  FP / (FP + FN)

    With FP=200 and FN=5000 that is 200/5200 = 0.0385. The measured
    optimum should land near this; a large divergence means either the
    probabilities are not as calibrated as Task 15 found, or the data
    is too sparse at the relevant score range.
    """
    return costs.false_positive / (costs.false_positive + costs.false_negative)


def three_way(y_true: np.ndarray, scores: np.ndarray, costs: CostModel,
              block_threshold: float, review_threshold: float) -> dict:
    """Approve / review / block, with a human in the middle band.

    A binary decision throws away the model's uncertainty. Scores in
    the middle are exactly the cases worth an analyst's time: too risky
    to approve silently, not certain enough to block a paying customer.
    """
    y = np.asarray(y_true).astype(bool)
    s = np.asarray(scores, dtype=float)

    block = s >= block_threshold
    review = (s >= review_threshold) & (s < block_threshold)
    approve = s < review_threshold

    n = len(y)
    missed = int((approve & y).sum())
    blocked_ok = int((block & ~y).sum())
    n_review = int(review.sum())
    fraud_in_review = int((review & y).sum())

    # Assume review catches fraud correctly - an analyst sees the case.
    total = (missed * costs.false_negative
             + blocked_ok * costs.false_positive
             + n_review * costs.review)

    return {
        "block_threshold": float(block_threshold),
        "review_threshold": float(review_threshold),
        "n_approved": int(approve.sum()),
        "n_review": n_review,
        "n_blocked": int(block.sum()),
        "review_rate": n_review / n if n else 0.0,
        "fraud_missed": missed,
        "fraud_in_review": fraud_in_review,
        "fraud_blocked": int((block & y).sum()),
        "legit_blocked": blocked_ok,
        "total_cost": float(total),
        "cost_per_1000": float(1000 * total / n) if n else 0.0,
        "reviews_per_day": n_review,
    }


def format_result(r: ThresholdResult, costs: CostModel, label: str = "") -> str:
    """Terminal report for one threshold. ASCII only."""
    out = []
    head = f"  threshold {r.threshold:.5f}"
    if label:
        head += f"   ({label})"
    out.append(head)
    out.append(f"    caught {r.tp:>5,} fraud   missed {r.fn:>5,}   "
               f"recall {r.recall:.4f}")
    out.append(f"    blocked {r.fp:>5,} legit   precision {r.precision:.4f}")
    out.append(f"    flagged {r.flagged:,} rows ({r.flag_rate * 100:.3f}% of traffic)")
    out.append(f"    cost Rs {r.total_cost:>12,.0f}   "
               f"(missed {r.fn:,} x {costs.false_negative:,.0f} + "
               f"blocked {r.fp:,} x {costs.false_positive:,.0f})")
    out.append(f"    cost per 1,000 transactions: Rs {r.cost_per_1000:,.2f}")
    return "\n".join(out)