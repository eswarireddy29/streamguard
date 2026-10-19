"""
src/streamguard/ml/metrics.py

Task 12.3 - evaluation metrics for a rare-event classifier.

Fraud here is ~0.380% of transactions. That single fact rules out
accuracy and makes PR-AUC, precision@k and per-pattern recall the
metrics that mean anything. Every number produced by this module is
reported alongside the random-model baseline, because a PR-AUC of 0.40
is meaningless until you know random scores 0.0038.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict

import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    roc_auc_score,
    precision_score,
    recall_score,
    f1_score,
    confusion_matrix,
)


@dataclass
class EvalResult:
    """Everything measured about one model on one block of data."""
    model: str
    block: str
    n: int
    n_fraud: int
    prevalence: float

    pr_auc: float
    pr_auc_random: float
    lift_over_random: float
    roc_auc: float

    k: int
    alerts_per_day: int
    precision_at_k: float
    recall_at_k: float
    fraud_caught_at_k: int

    accuracy_always_negative: float
    per_pattern_recall_at_k: dict = field(default_factory=dict)
    per_pattern_n: dict = field(default_factory=dict)

    binary_precision: float | None = None
    binary_recall: float | None = None
    binary_f1: float | None = None
    binary_flagged: int | None = None

    notes: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def precision_recall_at_k(y_true: np.ndarray, scores: np.ndarray, k: int
                          ) -> tuple[float, float, int]:
    """Take the k highest-scoring rows; report precision and recall there.

    Ties are broken by original order, which is chronological after the
    splitter sorts. That is arbitrary but deterministic - and a model
    with many tied scores (like the rules baseline) will show it here.
    """
    k = min(int(k), len(scores))
    if k <= 0:
        return 0.0, 0.0, 0
    # argsort ascending, so take the last k and reverse.
    top_idx = np.argsort(scores, kind="stable")[-k:]
    caught = int(y_true[top_idx].sum())
    total_fraud = int(y_true.sum())
    precision = caught / k
    recall = caught / total_fraud if total_fraud else 0.0
    return precision, recall, caught


def per_pattern_recall(y_true: np.ndarray, scores: np.ndarray,
                       fraud_type: pd.Series, k: int
                       ) -> tuple[dict, dict]:
    """For each fraud pattern: what fraction landed in the top k?

    This is the measurement your Task 10 note deferred to Task 15. If
    account_takeover recall is far below the others, the weak-feature
    diagnosis is confirmed and targeted features are justified. If it
    is comparable, the trees found interactions a mean-ratio comparison
    could not see - and no new features are needed.
    """
    k = min(int(k), len(scores))
    top_idx = np.argsort(scores, kind="stable")[-k:]
    flagged = np.zeros(len(scores), dtype=bool)
    flagged[top_idx] = True

    ft = pd.Series(fraud_type).reset_index(drop=True)
    is_fraud = pd.Series(y_true).reset_index(drop=True).astype(bool)
    flagged_s = pd.Series(flagged)

    recalls, counts = {}, {}
    for pattern in sorted(ft[is_fraud].dropna().unique()):
        mask = is_fraud & (ft == pattern)
        n = int(mask.sum())
        counts[str(pattern)] = n
        recalls[str(pattern)] = float(flagged_s[mask].mean()) if n else 0.0
    return recalls, counts


def evaluate(model_name: str, block_name: str, y_true: np.ndarray,
             scores: np.ndarray, fraud_type: pd.Series | None = None,
             n_days: int = 1, alerts_per_day: int = 100,
             binary_pred: np.ndarray | None = None,
             notes: list | None = None) -> EvalResult:
    """Full evaluation of one score vector.

    scores may be probabilities, decision values, or a rule count - the
    ranking metrics only need relative order, not calibration.
    """
    y_true = np.asarray(y_true).astype(int)
    scores = np.asarray(scores, dtype=float)
    notes = list(notes or [])

    n = len(y_true)
    n_fraud = int(y_true.sum())
    prevalence = n_fraud / n if n else 0.0

    # A score vector with no variation cannot rank anything.
    if np.all(scores == scores[0]) if n else False:
        notes.append("all scores identical - ranking metrics are degenerate")

    pr_auc = float(average_precision_score(y_true, scores)) if n_fraud else float("nan")
    try:
        roc = float(roc_auc_score(y_true, scores)) if n_fraud else float("nan")
    except ValueError:
        roc = float("nan")

    k = max(1, int(alerts_per_day * n_days))
    p_at_k, r_at_k, caught = precision_recall_at_k(y_true, scores, k)

    pp_recall, pp_n = ({}, {})
    if fraud_type is not None:
        pp_recall, pp_n = per_pattern_recall(y_true, scores, fraud_type, k)

    res = EvalResult(
        model=model_name,
        block=block_name,
        n=n,
        n_fraud=n_fraud,
        prevalence=prevalence,
        pr_auc=pr_auc,
        pr_auc_random=prevalence,
        lift_over_random=(pr_auc / prevalence) if prevalence else float("nan"),
        roc_auc=roc,
        k=k,
        alerts_per_day=alerts_per_day,
        precision_at_k=p_at_k,
        recall_at_k=r_at_k,
        fraud_caught_at_k=caught,
        accuracy_always_negative=1.0 - prevalence,
        per_pattern_recall_at_k=pp_recall,
        per_pattern_n=pp_n,
        notes=notes,
    )

    if binary_pred is not None:
        bp = np.asarray(binary_pred).astype(int)
        res.binary_precision = float(precision_score(y_true, bp, zero_division=0))
        res.binary_recall = float(recall_score(y_true, bp, zero_division=0))
        res.binary_f1 = float(f1_score(y_true, bp, zero_division=0))
        res.binary_flagged = int(bp.sum())

    return res


def format_result(r: EvalResult) -> str:
    """Human-readable block for the terminal. ASCII only (cmd code page)."""
    lines = []
    lines.append(f"--- {r.model}  on  {r.block} " + "-" * max(0, 44 - len(r.model) - len(r.block)))
    lines.append(f"  rows {r.n:,}   fraud {r.n_fraud:,}   prevalence {r.prevalence * 100:.3f}%")
    lines.append(f"  PR-AUC            {r.pr_auc:.4f}    (random = {r.pr_auc_random:.4f}, "
                 f"lift {r.lift_over_random:.1f}x)")
    lines.append(f"  ROC-AUC           {r.roc_auc:.4f}    (reported, not judged by)")
    lines.append(f"  precision@{r.k:<6}  {r.precision_at_k:.4f}    "
                 f"({r.fraud_caught_at_k:,} real fraud in the top {r.k:,})")
    lines.append(f"  recall@{r.k:<9}  {r.recall_at_k:.4f}    "
                 f"at {r.alerts_per_day} analyst reviews per day")
    if r.binary_precision is not None:
        lines.append(f"  binary flagged    {r.binary_flagged:,}   "
                     f"precision {r.binary_precision:.4f}  "
                     f"recall {r.binary_recall:.4f}  F1 {r.binary_f1:.4f}")
    if r.per_pattern_recall_at_k:
        lines.append(f"  per-pattern recall in top {r.k:,}:")
        for pat in sorted(r.per_pattern_recall_at_k):
            nn = r.per_pattern_n.get(pat, 0)
            rec = r.per_pattern_recall_at_k[pat]
            lines.append(f"      {pat:<22} {rec * 100:>6.1f}%   (n={nn:,})")
    for note in r.notes:
        lines.append(f"  NOTE: {note}")
    return "\n".join(lines)


def comparison_table(results: list[EvalResult]) -> str:
    """One row per model, so the baselines can be read side by side."""
    head = (f"  {'model':<22}{'PR-AUC':>9}{'lift':>8}{'ROC-AUC':>10}"
            f"{'prec@k':>9}{'recall@k':>10}")
    lines = [head, "  " + "-" * (len(head) - 2)]
    for r in results:
        lines.append(f"  {r.model:<22}{r.pr_auc:>9.4f}{r.lift_over_random:>7.1f}x"
                     f"{r.roc_auc:>10.4f}{r.precision_at_k:>9.4f}{r.recall_at_k:>10.4f}")
    return "\n".join(lines)