"""
src/streamguard/ml/baselines.py

Task 12.4 - three baselines that any real model must beat.

A PR-AUC of 0.72 means nothing on its own. Against a baseline of 0.21
it is an achievement; against 0.68 the extra complexity was not worth
building. These three exist so that Task 13's number has a yardstick.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from streamguard.ml.splitter import resolve_column
from streamguard.utils.logging_config import get_logger

log = get_logger(__name__)


class AlwaysNegativeBaseline:
    """Predicts 'not fraud' for everything.

    Exists to prove accuracy is the wrong metric. At 0.380% prevalence
    this scores 99.62% accuracy and catches zero fraud. Any stakeholder
    who asks for 'accuracy' should be shown this model first.
    """

    name = "always_negative"

    def fit(self, X, y):
        return self

    def score_samples(self, X) -> np.ndarray:
        return np.zeros(len(X), dtype=float)

    def predict(self, X) -> np.ndarray:
        return np.zeros(len(X), dtype=int)


@dataclass
class RuleThresholds:
    """The rules a bank would have written before ML.

    Deliberately the thresholds from the project record, not tuned, so
    this is a fair picture of pre-ML practice. If they are later tuned,
    tune on TRAIN or VAL only - never on test.
    """
    velocity_5m: float = 5.0        # more than 5 txns in the prior 5 minutes
    speed_kmh: float = 900.0        # faster than a commercial aircraft
    amount_ratio: float = 20.0      # more than 20x this card's mean amount


class RuleBaseline:
    """Three OR-ed rules. Score = how many fired (0-3).

    Why a count rather than a yes/no: a binary output cannot be ranked,
    so precision@k would be undefined. Counting fired rules gives a
    crude ordering while staying faithful to how rule systems behave.
    The pure binary decision is returned separately by predict().

    Column names are resolved at runtime because they were fixed in
    Task 10 and this module should adapt to them, not assume them.
    """

    name = "rules"

    VELOCITY_CANDIDATES = [
        "txn_count_5m", "txn_count_5min", "card_txn_count_5m", "velocity_5m",
    ]
    SPEED_CANDIDATES = [
        "implied_speed_kmh", "implied_speed", "speed_kmh",
    ]
    RATIO_CANDIDATES = [
        "amount_to_card_mean_ratio", "amount_card_mean_ratio",
        "amount_ratio_card_mean", "card_amount_ratio", "amount_vs_card_mean",
    ]

    def __init__(self, thresholds: RuleThresholds | None = None):
        self.t = thresholds or RuleThresholds()
        self.cols: dict[str, str] = {}

    def fit(self, X: pd.DataFrame, y=None):
        """Rules have nothing to learn - fit only resolves column names."""
        self.cols = {
            "velocity": resolve_column(X, self.VELOCITY_CANDIDATES, "5-minute velocity"),
            "speed": resolve_column(X, self.SPEED_CANDIDATES, "implied speed"),
            "ratio": resolve_column(X, self.RATIO_CANDIDATES, "amount / card mean"),
        }
        log.info("rule_columns_resolved", **self.cols)
        return self

    def _fired(self, X: pd.DataFrame) -> pd.DataFrame:
        if not self.cols:
            self.fit(X)
        return pd.DataFrame({
            "velocity": X[self.cols["velocity"]] > self.t.velocity_5m,
            "speed": X[self.cols["speed"]] > self.t.speed_kmh,
            "ratio": X[self.cols["ratio"]] > self.t.amount_ratio,
        })

    def score_samples(self, X: pd.DataFrame) -> np.ndarray:
        return self._fired(X).sum(axis=1).to_numpy().astype(float)

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return self._fired(X).any(axis=1).to_numpy().astype(int)

    def rule_breakdown(self, X: pd.DataFrame, y: np.ndarray) -> pd.DataFrame:
        """How each rule performs alone - which ones actually carry weight."""
        fired = self._fired(X)
        y = np.asarray(y).astype(bool)
        rows = []
        for rule in fired.columns:
            f = fired[rule].to_numpy()
            n_flag = int(f.sum())
            tp = int((f & y).sum())
            rows.append({
                "rule": rule,
                "flagged": n_flag,
                "true_fraud": tp,
                "precision": tp / n_flag if n_flag else 0.0,
                "recall": tp / int(y.sum()) if y.sum() else 0.0,
            })
        return pd.DataFrame(rows)


class LogisticBaseline:
    """Scaled logistic regression - a LINEAR model.

    It can weight each feature, but it cannot learn interactions:
    'large amount AND new device AND 3am' is invisible to it unless
    that combination happens to be linearly separable. That is exactly
    what makes it the right yardstick for LightGBM. If trees barely
    beat this, the 49 features hold no useful interactions.

    class_weight='balanced' is on because at 0.38% prevalence an
    unweighted model minimises its loss by predicting 'never fraud'.
    The cost: output probabilities are no longer calibrated and will
    read too high. Ranking metrics are unaffected; calibration is
    Task 15's job. Do not quote these probabilities as real chances.
    """

    name = "logistic_regression"

    def __init__(self, max_iter: int = 1000, random_state: int = 42):
        self.pipe = Pipeline([
            # Fitted on TRAIN ONLY. Fitting the scaler on train+val
            # would leak validation statistics into training.
            ("scale", StandardScaler()),
            ("clf", LogisticRegression(
                max_iter=max_iter,
                class_weight="balanced",
                solver="lbfgs",
                n_jobs=-1,
                random_state=random_state,
            )),
        ])

    def fit(self, X: pd.DataFrame, y: np.ndarray):
        log.info("fitting_logistic", rows=len(X), features=X.shape[1])
        self.pipe.fit(X, y)
        return self

    def score_samples(self, X: pd.DataFrame) -> np.ndarray:
        return self.pipe.predict_proba(X)[:, 1]

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return self.pipe.predict(X)

    def coefficients(self, feature_names: list[str]) -> pd.DataFrame:
        """Largest absolute coefficients = features the linear model leans on.

        NOT the same as importance in a tree model, and NOT causal.
        Useful as a cross-check against Task 18's SHAP values.
        """
        coef = self.pipe.named_steps["clf"].coef_[0]
        return (pd.DataFrame({"feature": feature_names, "coefficient": coef})
                .assign(abs_coef=lambda d: d["coefficient"].abs())
                .sort_values("abs_coef", ascending=False)
                .drop(columns="abs_coef")
                .reset_index(drop=True))