"""
src/streamguard/ml/tuning.py

Task 14.2 - random hyperparameter search.

Six settings, searched randomly rather than exhaustively: a full grid
would be 15,625 fits at minutes each. Random search finds near-best
combinations in 30-40 tries because usually only two or three settings
matter much.

Every trial trains on TRAIN and is judged on VALIDATION. Test is never
loaded here.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

from streamguard.utils.logging_config import get_logger

log = get_logger(__name__)


# The search space. Each entry is a list of candidate values.
#
# num_leaves / max_depth / min_child_samples are the CAPACITY dials -
# how finely a tree can carve up the data. More capacity fits training
# better and generalises worse.
#
# subsample / colsample_bytree inject randomness: each tree sees only a
# fraction of rows and columns, which reduces overfitting.
#
# reg_lambda is L2 regularisation - it penalises large leaf values,
# pulling predictions toward the average.
SEARCH_SPACE = {
    "num_leaves": [7, 15, 31, 63, 127],
    "max_depth": [3, 5, 7, 10, -1],
    "min_child_samples": [20, 50, 100, 200, 500],
    "subsample": [0.6, 0.7, 0.8, 0.9, 1.0],
    "colsample_bytree": [0.5, 0.6, 0.7, 0.8, 1.0],
    "reg_lambda": [0.0, 1.0, 5.0, 20.0, 100.0],
}

# Fixed across every trial, so the search isolates the six above.
FIXED = {
    "objective": "binary",
    "metric": "average_precision",
    "learning_rate": 0.05,
    "n_estimators": 2000,
    "subsample_freq": 1,
    "reg_alpha": 0.0,
    # Task 14.1 measured this: is_unbalance=True scored 0.9201 with a
    # 0.0799 gap over 1,399 trees; False scored 0.9495 with a 0.0458
    # gap over 116. At 0.368% prevalence LightGBM finds the signal
    # without reweighting - and unweighted output stays CALIBRATED,
    # which Task 15 and Task 16 both need.
    "is_unbalance": False,
    "verbosity": -1,
}

EARLY_STOPPING_ROUNDS = 100


@dataclass
class Trial:
    """One hyperparameter combination and what it scored."""
    trial: int
    params: dict
    pr_auc: float
    train_pr_auc: float
    gap: float
    best_iteration: int
    seconds: float

    def line(self) -> str:
        p = self.params
        return (f"  {self.trial:>3}  PR-AUC {self.pr_auc:.4f}  "
                f"gap {self.gap:.4f}  trees {self.best_iteration:>4}  "
                f"leaves {p['num_leaves']:>3} depth {p['max_depth']:>3} "
                f"minchild {p['min_child_samples']:>3} "
                f"sub {p['subsample']:.1f} col {p['colsample_bytree']:.1f} "
                f"l2 {p['reg_lambda']:>5.1f}")


@dataclass
class SearchResult:
    """Every trial, plus the winner."""
    n_trials: int
    baseline_pr_auc: float
    baseline_gap: float
    best_params: dict = field(default_factory=dict)
    best_pr_auc: float = 0.0
    best_gap: float = 0.0
    best_iteration: int = 0
    trials: list = field(default_factory=list)
    total_seconds: float = 0.0

    def save(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        return path

    def table(self, top: int = 10) -> str:
        rows = sorted(self.trials, key=lambda t: -t["pr_auc"])[:top]
        out = [f"  {'rank':<6}{'PR-AUC':>9}{'gap':>8}{'trees':>7}"
               f"{'leaves':>8}{'depth':>7}{'minchild':>10}{'l2':>7}"]
        out.append("  " + "-" * 60)
        for i, t in enumerate(rows, 1):
            p = t["params"]
            out.append(f"  {i:<6}{t['pr_auc']:>9.4f}{t['gap']:>8.4f}"
                       f"{t['best_iteration']:>7}{p['num_leaves']:>8}"
                       f"{p['max_depth']:>7}{p['min_child_samples']:>10}"
                       f"{p['reg_lambda']:>7.1f}")
        return "\n".join(out)


def sample_params(rng: np.random.Generator) -> dict:
    """One random draw from the search space."""
    return {k: (v[int(rng.integers(0, len(v)))]) for k, v in SEARCH_SPACE.items()}


def run_trial(trial_no: int, params: dict,
              X_train: pd.DataFrame, y_train: np.ndarray,
              X_val: pd.DataFrame, y_val: np.ndarray,
              n_jobs: int = 6, seed: int = 42) -> Trial:
    """Fit one combination and score it on validation."""
    full = {**FIXED, **params, "n_jobs": n_jobs, "random_state": seed}

    t0 = time.perf_counter()
    model = lgb.LGBMClassifier(**full)
    model.fit(
        X_train, y_train,
        eval_set=[(X_val, y_val)],
        eval_names=["val"],
        callbacks=[lgb.early_stopping(EARLY_STOPPING_ROUNDS, verbose=False)],
    )
    elapsed = time.perf_counter() - t0

    val_ap = float(average_precision_score(
        y_val, model.predict_proba(X_val)[:, 1]))
    train_ap = float(average_precision_score(
        y_train, model.predict_proba(X_train)[:, 1]))

    return Trial(
        trial=trial_no,
        params=params,
        pr_auc=val_ap,
        train_pr_auc=train_ap,
        gap=train_ap - val_ap,
        best_iteration=int(model.best_iteration_ or 0),
        seconds=elapsed,
    )


def random_search(X_train: pd.DataFrame, y_train: np.ndarray,
                  X_val: pd.DataFrame, y_val: np.ndarray,
                  n_trials: int = 30, n_jobs: int = 6, seed: int = 42,
                  baseline_pr_auc: float = 0.9495,
                  baseline_gap: float = 0.0458,
                  on_trial=None) -> SearchResult:
    """Try n_trials random combinations; keep the best.

    SELECTION RULE: highest PR-AUC wins, but a tie within 0.002 goes to
    the smaller gap. A model scoring 0.950 with a 0.02 gap beats 0.951
    with a 0.09 gap - it is likelier to hold up on the sealed test set.
    """
    rng = np.random.default_rng(seed)
    result = SearchResult(n_trials=n_trials,
                          baseline_pr_auc=baseline_pr_auc,
                          baseline_gap=baseline_gap)

    started = time.perf_counter()
    seen: set = set()

    for i in range(1, n_trials + 1):
        # Avoid repeating an identical combination.
        for _ in range(20):
            params = sample_params(rng)
            key = tuple(sorted(params.items()))
            if key not in seen:
                seen.add(key)
                break

        t = run_trial(i, params, X_train, y_train, X_val, y_val, n_jobs, seed)
        result.trials.append(asdict(t))

        if on_trial is not None:
            on_trial(t, result)

        better = t.pr_auc > result.best_pr_auc
        tie = abs(t.pr_auc - result.best_pr_auc) < 0.002 and t.gap < result.best_gap
        if better or tie:
            result.best_pr_auc = t.pr_auc
            result.best_gap = t.gap
            result.best_params = dict(t.params)
            result.best_iteration = t.best_iteration

    result.total_seconds = time.perf_counter() - started
    return result


def final_params(best: dict, n_jobs: int = 6, seed: int = 42) -> dict:
    """The winning combination as a complete LightGBM parameter dict."""
    return {**FIXED, **best, "n_jobs": n_jobs, "random_state": seed}