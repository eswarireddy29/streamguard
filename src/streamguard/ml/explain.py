"""
src/streamguard/ml/explain.py

Task 18B - why did THIS transaction score 0.87?

Feature importance says what the model uses overall. It cannot tell an
analyst why one specific case was flagged. SHAP decomposes a single
prediction into per-feature contributions that SUM to that prediction,
so the explanation is complete rather than a top-3 guess.

This feeds the Task 26 investigation view: an analyst sees "flagged
because velocity was 8x normal AND the device is new", not a bare score.

TreeSHAP is exact for tree models and fast enough for the Phase E
latency budget - no sampling, no approximation.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd
import shap


@dataclass
class Explanation:
    """One transaction's explanation."""
    prediction: float
    base_value: float
    top_positive: list   # pushed the score UP (toward fraud)
    top_negative: list   # pushed it DOWN (toward legitimate)
    total_shap: float

    def to_dict(self) -> dict:
        return asdict(self)

    def sentence(self, n: int = 3) -> str:
        """Plain-English summary for an analyst."""
        if not self.top_positive:
            return "No feature pushed this transaction toward fraud."
        parts = [f"{f} = {v:,.2f}" for f, v, _ in self.top_positive[:n]]
        return ("Flagged mainly because " + ", ".join(parts[:-1])
                + (" and " if len(parts) > 1 else "") + parts[-1]
                if len(parts) > 1 else f"Flagged mainly because {parts[0]}")


class ShapExplainer:
    """TreeSHAP over a LightGBM booster.

    Exact for trees, so there is no sampling error and no background
    dataset to choose. Cost is roughly proportional to tree count and
    depth, which Task 14 kept small (90-200 trees, depth 10).
    """

    def __init__(self, booster, feature_names: list[str]):
        self.booster = booster
        self.feature_names = list(feature_names)
        self.explainer = shap.TreeExplainer(booster)

    def shap_values(self, X: pd.DataFrame) -> np.ndarray:
        """Per-feature contributions, shape (rows, features)."""
        vals = self.explainer.shap_values(X)
        # Binary LightGBM may return a list of two arrays; take class 1.
        if isinstance(vals, list):
            vals = vals[1] if len(vals) > 1 else vals[0]
        return np.asarray(vals)

    @property
    def base_value(self) -> float:
        bv = self.explainer.expected_value
        if isinstance(bv, (list, np.ndarray)):
            bv = bv[1] if len(np.atleast_1d(bv)) > 1 else np.atleast_1d(bv)[0]
        return float(bv)

    def explain_one(self, X: pd.DataFrame, i: int, top: int = 5
                    ) -> Explanation:
        """Explain a single row by position."""
        row = X.iloc[[i]]
        vals = self.shap_values(row)[0]
        pred = float(np.asarray(self.booster.predict(row))[0])

        pairs = [(self.feature_names[j], float(row.iloc[0, j]), float(vals[j]))
                 for j in range(len(vals))]

        pos = sorted([p for p in pairs if p[2] > 0],
                     key=lambda p: -p[2])[:top]
        neg = sorted([p for p in pairs if p[2] < 0],
                     key=lambda p: p[2])[:top]

        return Explanation(
            prediction=pred,
            base_value=self.base_value,
            top_positive=pos,
            top_negative=neg,
            total_shap=float(vals.sum()),
        )

    def global_importance(self, X: pd.DataFrame,
                          sample: int = 5000) -> pd.DataFrame:
        """Mean |SHAP| per feature - the honest global ranking.

        Unlike gain importance, this does not split credit arbitrarily
        between correlated features: each row's contribution is
        attributed to the feature that actually moved that prediction.
        """
        if len(X) > sample:
            X = X.sample(sample, random_state=42)
        vals = self.shap_values(X)
        mean_abs = np.abs(vals).mean(axis=0)
        total = mean_abs.sum()
        return (pd.DataFrame({
                    "feature": self.feature_names,
                    "mean_abs_shap": mean_abs,
                    "pct": 100 * mean_abs / total if total else 0.0,
                })
                .sort_values("mean_abs_shap", ascending=False)
                .reset_index(drop=True))


def verify_additivity(explainer: ShapExplainer, X: pd.DataFrame,
                      n: int = 100, tol: float = 1e-3) -> dict:
    """SHAP values plus the base value must equal the prediction.

    This is the mathematical guarantee that makes SHAP trustworthy. If
    it fails, the explanations are wrong and must not be shown to an
    analyst. Checked rather than assumed.

    Note: LightGBM's SHAP values are in LOG-ODDS space, so they are
    compared against the raw score, not the probability.
    """
    sub = X.iloc[:n]
    vals = explainer.shap_values(sub)
    raw = np.asarray(explainer.booster.predict(sub, raw_score=True))
    reconstructed = vals.sum(axis=1) + explainer.base_value
    diff = np.abs(reconstructed - raw)
    return {
        "n_checked": int(n),
        "max_difference": float(diff.max()),
        "mean_difference": float(diff.mean()),
        "passes": bool(diff.max() < tol),
        "tolerance": tol,
    }