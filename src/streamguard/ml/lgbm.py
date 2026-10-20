"""
src/streamguard/ml/lgbm.py

Task 13 - gradient boosted trees.

Interface matches the Task 12 baselines (fit / score_samples / predict)
so it drops into the existing metrics module unchanged.

WHY TREES ARE EXPECTED TO HELP HERE, specifically:
The Task 12.5b diagnostic found implied_speed_kmh resolves to
'low = fraud', because card_testing is 53% of fraud and runs at near
zero speed. geo_impossible sits at the opposite extreme (4,210 km/h).
A linear model picks ONE direction per feature and so ranks
geo_impossible against itself - it scored only 80% recall there.
A tree can place 'speed < 1' and 'speed > 900' in separate leaves.
That is the hypothesis this task tests.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from streamguard.utils.logging_config import get_logger

log = get_logger(__name__)


@dataclass
class LGBMConfig:
    """Starting hyperparameters. Task 14 tunes these; these are not final.

    Chosen conservatively because there are only ~2,129 fraud rows in
    training. A model with too much capacity will memorise individual
    frauds rather than learn patterns.
    """

    # --- capacity controls (the overfitting dials) ---
    num_leaves: int = 31           # max leaves per tree; more = finer, riskier
    max_depth: int = -1            # -1 = unlimited, bounded by num_leaves
    min_child_samples: int = 100   # a leaf needs 100 rows; blocks memorising
                                   # a handful of specific frauds

    # --- learning rate and count ---
    learning_rate: float = 0.05    # small steps; more trees, better generalising
    n_estimators: int = 2000       # an upper bound - early stopping decides
    early_stopping_rounds: int = 100

    # --- randomness, which reduces overfitting ---
    subsample: float = 0.8         # each tree sees 80% of rows
    subsample_freq: int = 1        # resample every iteration
    colsample_bytree: float = 0.8  # each tree sees 80% of features

    # --- regularisation ---
    reg_alpha: float = 0.0         # L1
    reg_lambda: float = 1.0        # L2

    # --- class imbalance ---
    # LightGBM's equivalent of class_weight='balanced'. Prevents the
    # degenerate 'never fraud' solution at 0.385% prevalence.
    # COST: output probabilities are NOT calibrated and read too high.
    # Ranking metrics are unaffected. Calibration is Task 15.
    is_unbalance: bool = True

    # --- machine limits ---
    # 6 of 12 threads, NOT -1. 8 GB RAM: all 12 threads on 552k x 49
    # risks paging, which is slower than using fewer threads.
    n_jobs: int = 6

    random_state: int = 42
    verbosity: int = -1

    def to_params(self) -> dict:
        return {
            "objective": "binary",
            "metric": "average_precision",  # PR-AUC: stop on what we judge by
            "num_leaves": self.num_leaves,
            "max_depth": self.max_depth,
            "min_child_samples": self.min_child_samples,
            "learning_rate": self.learning_rate,
            "n_estimators": self.n_estimators,
            "subsample": self.subsample,
            "subsample_freq": self.subsample_freq,
            "colsample_bytree": self.colsample_bytree,
            "reg_alpha": self.reg_alpha,
            "reg_lambda": self.reg_lambda,
            "is_unbalance": self.is_unbalance,
            "n_jobs": self.n_jobs,
            "random_state": self.random_state,
            "verbosity": self.verbosity,
        }


@dataclass
class TrainingRecord:
    """Everything needed to reproduce or audit this training run."""
    config: dict
    n_train: int
    n_train_fraud: int
    n_val: int
    n_val_fraud: int
    n_features: int
    feature_names: list
    best_iteration: int
    n_estimators_requested: int
    stopped_early: bool
    best_val_score: float
    train_seconds: float
    lightgbm_version: str
    evals: dict = field(default_factory=dict)

    def save(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        return path


class LGBMModel:
    """Gradient boosted trees, same interface as the Task 12 baselines."""

    name = "lightgbm"

    def __init__(self, config: LGBMConfig | None = None):
        self.cfg = config or LGBMConfig()
        self.model: lgb.LGBMClassifier | None = None
        self.booster: lgb.Booster | None = None
        self.record: TrainingRecord | None = None
        self.feature_names: list[str] = []

    def fit(self, X: pd.DataFrame, y: np.ndarray,
            X_val: pd.DataFrame | None = None,
            y_val: np.ndarray | None = None) -> "LGBMModel":
        """Train, using validation for early stopping.

        IMPORTANT: validation is used to decide WHEN TO STOP, which is a
        mild form of fitting to it. That is exactly why validation and
        test are different blocks. The test set still has never been
        touched by anything.
        """
        import time

        self.feature_names = list(X.columns)
        params = self.cfg.to_params()
        self.model = lgb.LGBMClassifier(**params)

        callbacks = []
        eval_set = None
        if X_val is not None and y_val is not None:
            eval_set = [(X, y), (X_val, y_val)]
            callbacks = [
                lgb.early_stopping(self.cfg.early_stopping_rounds, verbose=False),
                lgb.log_evaluation(period=100),
            ]

        log.info("fitting_lightgbm", rows=len(X), features=X.shape[1],
                 fraud=int(y.sum()))
        t0 = time.perf_counter()
        self.model.fit(
            X, y,
            eval_set=eval_set,
            eval_names=["train", "val"] if eval_set else None,
            callbacks=callbacks,
        )
        elapsed = time.perf_counter() - t0

        best_iter = int(getattr(self.model, "best_iteration_", 0) or
                        self.cfg.n_estimators)
        stopped_early = best_iter < self.cfg.n_estimators

        evals = {}
        best_score = float("nan")
        if hasattr(self.model, "evals_result_") and self.model.evals_result_:
            raw = self.model.evals_result_
            for split, metrics in raw.items():
                for metric, values in metrics.items():
                    evals[f"{split}_{metric}"] = [float(v) for v in values]
            for key in ("val_average_precision", "valid_1_average_precision"):
                if key in evals and evals[key]:
                    best_score = max(evals[key])
                    break

        self.record = TrainingRecord(
            config=asdict(self.cfg),
            n_train=len(X),
            n_train_fraud=int(y.sum()),
            n_val=len(X_val) if X_val is not None else 0,
            n_val_fraud=int(y_val.sum()) if y_val is not None else 0,
            n_features=X.shape[1],
            feature_names=self.feature_names,
            best_iteration=best_iter,
            n_estimators_requested=self.cfg.n_estimators,
            stopped_early=stopped_early,
            best_val_score=best_score,
            train_seconds=elapsed,
            lightgbm_version=lgb.__version__,
            evals=evals,
        )
        log.info("lightgbm_fitted", seconds=round(elapsed, 1),
                 best_iteration=best_iter, stopped_early=stopped_early)
        return self

    def score_samples(self, X: pd.DataFrame) -> np.ndarray:
        """Fraud probability.

        Calibration depends on is_unbalance: with it True the output is
        NOT calibrated and reads too high; Task 14.1 set it False, so
        the tuned model's probabilities are usable as probabilities.
        """
        booster = getattr(self, "booster", None)
        if booster is not None:
            return np.asarray(booster.predict(X), dtype=float)
        if self.model is None:
            raise RuntimeError("call fit() first")
        return self.model.predict_proba(X)[:, 1]

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        if self.model is None:
            raise RuntimeError("call fit() first")
        return self.model.predict(X)

    def importance(self, kind: str = "gain") -> pd.DataFrame:
        """Feature importance.

        'gain'  = total improvement in the objective from splits on this
                  feature. This is the meaningful one.
        'split' = how many times it was split on. A feature can be split
                  on often while each split barely helps.

        NOT causal, and not the same as SHAP (Task 18). Importance says
        what the model used, not what matters in the world.
        """
        booster = getattr(self, "booster", None)
        if booster is None:
            if self.model is None:
                raise RuntimeError("call fit() first")
            booster = self.model.booster_

        vals = booster.feature_importance(importance_type=kind)
        total = vals.sum()
        return (pd.DataFrame({
                    "feature": self.feature_names,
                    kind: vals,
                    "pct": 100 * vals / total if total else 0.0,
                })
                .sort_values(kind, ascending=False)
                .reset_index(drop=True))

    def save(self, path: Path) -> Path:
        """Save the booster as plain text.

        Text, not pickle: a pickle can silently break when a library
        version changes, and loading one executes code. LightGBM's own
        text format is stable and inspectable - you can open it and read
        the trees.
        """
        if self.model is None:
            raise RuntimeError("call fit() first")
        path.parent.mkdir(parents=True, exist_ok=True)
        self.model.booster_.save_model(str(path),
                                       num_iteration=self.model.best_iteration_)
        return path

    @classmethod
    def load(cls, path: Path) -> "LGBMModel":
        """Load a saved booster.

        BUG FIXED (Task 15.2): the old version attached a booster to a
        bare LGBMClassifier whose internal _n_features was never set, so
        predict_proba() raised "Model n_features_ is -1". Reading
        importances still worked, which is why Task 13 did not catch it.
        A loaded model now predicts through the booster directly.
        """
        obj = cls()
        obj.model = None
        obj.booster = lgb.Booster(model_file=str(path))
        obj.feature_names = list(obj.booster.feature_name())
        return obj