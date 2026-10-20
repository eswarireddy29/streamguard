"""
src/streamguard/ml/anomaly.py

Task 17 - catching fraud the supervised model has never seen.

LightGBM learned five patterns from labels. A sixth pattern invented
next month would score low and be approved - a supervised model can
only catch what it was shown.

An unsupervised detector learns what NORMAL looks like and flags
distance from it. It needs no labels, so a new attack is just as
anomalous as an old one. The cost is precision: unusual is not the
same as fraudulent, and most unusual transactions are legitimate.

TRAINING RULE: these are fitted on NORMAL ROWS ONLY. Including fraud
in the training data teaches the detector that fraud is normal, which
is the whole failure mode.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler, QuantileTransformer
from sklearn.pipeline import Pipeline

from streamguard.utils.logging_config import get_logger

log = get_logger(__name__)


@dataclass
class AnomalyConfig:
    """Shared settings.

    contamination is the fraction expected to be anomalous. It sets
    where the decision boundary falls, not how rows are ranked, so
    ranking metrics (PR-AUC) are unaffected by it.

    8 GB note: Isolation Forest holds max_samples rows per tree, not
    the whole dataset, so memory stays bounded regardless of input size.
    """
    n_estimators: int = 200
    max_samples: int = 25_000
    contamination: float = 0.01
    random_state: int = 42
    n_jobs: int = 6


class IsolationForestDetector:
    """Random splits isolate outliers faster than normal points.

    Intuition: to isolate a point in a dense cluster you need many
    splits; a point far from everything is cut off in one or two. The
    average number of splits needed IS the anomaly score.

    No distance metric, no distribution assumption, and it scales to
    hundreds of thousands of rows on CPU - which matters here.
    """

    name = "isolation_forest"

    def __init__(self, config: AnomalyConfig | None = None):
        self.cfg = config or AnomalyConfig()
        self.pipe: Pipeline | None = None
        self.feature_names: list[str] = []

    def fit(self, X: pd.DataFrame, y=None) -> "IsolationForestDetector":
        """Fit on NORMAL rows only. y is ignored - it is unsupervised.

        The caller is responsible for passing normal-only data. See
        fit_on_normal() below for the safe version.
        """
        self.feature_names = list(X.columns)
        self.pipe = Pipeline([
            # Quantile transform rather than standard scaling: amounts
            # are lognormal with a long tail, and a few huge values
            # would otherwise dominate every split.
            ("quantile", QuantileTransformer(
                output_distribution="normal",
                n_quantiles=min(1000, len(X)),
                random_state=self.cfg.random_state,
            )),
            ("iso", IsolationForest(
                n_estimators=self.cfg.n_estimators,
                max_samples=min(self.cfg.max_samples, len(X)),
                contamination=self.cfg.contamination,
                random_state=self.cfg.random_state,
                n_jobs=self.cfg.n_jobs,
            )),
        ])
        log.info("fitting_isolation_forest", rows=len(X),
                 features=X.shape[1])
        self.pipe.fit(X)
        return self

    def score_samples(self, X: pd.DataFrame) -> np.ndarray:
        """Higher = more anomalous.

        sklearn returns NEGATIVE scores where lower means more
        anomalous, so the sign is flipped to match every other
        score_samples() in this project (higher = more suspicious).
        """
        if self.pipe is None:
            raise RuntimeError("call fit() first")
        return -self.pipe.named_steps["iso"].score_samples(
            self.pipe.named_steps["quantile"].transform(X))

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """1 = anomalous, 0 = normal, at the contamination cutoff."""
        if self.pipe is None:
            raise RuntimeError("call fit() first")
        raw = self.pipe.predict(X)   # sklearn: -1 outlier, 1 inlier
        return (raw == -1).astype(int)


class MahalanobisDetector:
    """Distance from the centre of normal traffic, accounting for
    correlation between features.

    Euclidean distance treats every feature as independent. Mahalanobis
    uses the covariance matrix, so two correlated features moving
    together counts as ordinary, while one moving without the other is
    anomalous. That is a better model of "unusual behaviour".

    Assumes roughly elliptical data, which is a real limitation - but
    it is cheap, deterministic and a useful contrast to the forest.
    """

    name = "mahalanobis"

    def __init__(self, config: AnomalyConfig | None = None):
        self.cfg = config or AnomalyConfig()
        self.scaler: StandardScaler | None = None
        self.mean: np.ndarray | None = None
        self.inv_cov: np.ndarray | None = None
        self.feature_names: list[str] = []

    def fit(self, X: pd.DataFrame, y=None) -> "MahalanobisDetector":
        self.feature_names = list(X.columns)
        self.scaler = StandardScaler()
        Z = self.scaler.fit_transform(X)

        self.mean = Z.mean(axis=0)
        cov = np.cov(Z, rowvar=False)

        # Ridge term: some features are constant or collinear, which
        # makes the covariance matrix singular and uninvertible.
        cov += np.eye(cov.shape[0]) * 1e-6
        self.inv_cov = np.linalg.pinv(cov)

        log.info("fitting_mahalanobis", rows=len(X), features=X.shape[1])
        return self

    def score_samples(self, X: pd.DataFrame) -> np.ndarray:
        if self.scaler is None:
            raise RuntimeError("call fit() first")
        Z = self.scaler.transform(X)
        d = Z - self.mean
        # Row-wise quadratic form, chunked to bound memory on 8 GB.
        out = np.empty(len(Z), dtype=float)
        step = 50_000
        for i in range(0, len(Z), step):
            chunk = d[i:i + step]
            out[i:i + step] = np.einsum("ij,jk,ik->i", chunk, self.inv_cov, chunk)
        return out

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        s = self.score_samples(X)
        cutoff = np.quantile(s, 1 - self.cfg.contamination)
        return (s >= cutoff).astype(int)


def fit_on_normal(detector, X: pd.DataFrame, y: np.ndarray):
    """Fit a detector using ONLY the rows labelled normal.

    This is the safe entry point. Fitting on everything would teach the
    detector that fraud is part of normal traffic, which defeats the
    purpose. The labels are used to SELECT training rows, never as a
    feature - the detector itself stays unsupervised.
    """
    mask = np.asarray(y).astype(bool)
    X_normal = X.loc[~mask]
    log.info("fitting_on_normal_only", total=len(X), normal=len(X_normal),
             fraud_excluded=int(mask.sum()))
    return detector.fit(X_normal)