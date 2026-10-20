"""
scripts/explain_model.py

Task 18B - SHAP explanations for the graph model.

    python scripts/explain_model.py
    python scripts/explain_model.py --tag v5 --examples 5
"""

from __future__ import annotations

import json
from datetime import datetime

import lightgbm as lgb
import numpy as np
import pandas as pd
import typer

from streamguard.ml.splitter import add_day_index, resolve_column, PROJECT_ROOT
from streamguard.ml.explain import ShapExplainer, verify_additivity
from streamguard.features.computer import FEATURE_NAMES
from streamguard.features.graph import GRAPH_FEATURE_NAMES
from streamguard.utils.logging_config import get_logger, setup_logging

app = typer.Typer(add_completion=False)
log = get_logger(__name__)

PROCESSED = PROJECT_ROOT / "data" / "processed"
MODELS_DIR = PROJECT_ROOT / "models"
REPORTS_DIR = PROJECT_ROOT / "reports"
LINE = "=" * 72

DEAD = ["ring_size", "ring_fraud_density"]
TRAIN_DAYS, VAL_DAYS = 63, 13


@app.command()
def main(
    tag: str = typer.Option("v5"),
    examples: int = typer.Option(3, help="Cases to explain in detail"),
    sample: int = typer.Option(5000, help="Rows for the global ranking"),
) -> None:
    setup_logging()
    model_path = MODELS_DIR / f"lgbm_{tag}.txt"
    if not model_path.exists():
        print(f"ERROR: {model_path} not found.")
        raise typer.Exit(1)

    print(LINE)
    print(f"TASK 18B - SHAP EXPLANATIONS  ({model_path.name})")
    print(LINE)

    booster = lgb.Booster(model_file=str(model_path))
    cols = list(booster.feature_name())

    raw = pd.read_parquet(PROCESSED / "features_graph.parquet")
    df, _, _ = add_day_index(raw)
    label_col = resolve_column(df, ["is_fraud", "label", "y"], "fraud label")

    train_hi = TRAIN_DAYS - 1
    va = df[(df["_day"] > train_hi) & (df["_day"] <= train_hi + VAL_DAYS)] \
        .sort_values("_local_time", kind="mergesort").reset_index(drop=True)

    X = va[cols].astype("float32")
    y = va[label_col].to_numpy().astype(bool)
    ft = va["fraud_type"] if "fraud_type" in va.columns else None

    print()
    print(f"  model features: {len(cols)}")
    print(f"  validation rows: {len(X):,}  fraud: {int(y.sum()):,}")

    explainer = ShapExplainer(booster, cols)

    # ---- 1. additivity ------------------------------------------------
    print()
    print(LINE)
    print("1. ADDITIVITY CHECK")
    print(LINE)
    print()
    print("  SHAP values + base value must equal the raw prediction.")
    print("  That identity is what makes the explanation complete rather")
    print("  than a plausible-looking guess. Checked, not assumed.")
    print()
    v = verify_additivity(explainer, X, n=100)
    print(f"  rows checked      {v['n_checked']}")
    print(f"  max difference    {v['max_difference']:.3e}")
    print(f"  mean difference   {v['mean_difference']:.3e}")
    print(f"  tolerance         {v['tolerance']:.0e}")
    print()
    print("  PASS - explanations are mathematically sound."
          if v["passes"] else
          "  FAIL - do NOT show these explanations to an analyst.")

    # ---- 2. global ranking ---------------------------------------------
    print()
    print(LINE)
    print("2. GLOBAL IMPORTANCE BY MEAN |SHAP|")
    print(LINE)
    print()
    print(f"  (sampled {min(sample, len(X)):,} validation rows)")
    print()
    g = explainer.global_importance(X, sample=sample)
    print(g.head(15).to_string(index=False,
                               formatters={"mean_abs_shap": "{:.5f}".format,
                                           "pct": "{:.2f}".format}))

    gain = pd.DataFrame({"feature": cols,
                         "gain": booster.feature_importance("gain")})
    gain["gain_rank"] = gain["gain"].rank(ascending=False).astype(int)
    merged = g.merge(gain[["feature", "gain_rank"]], on="feature")
    merged["shap_rank"] = merged.index + 1
    merged["moved"] = merged["gain_rank"] - merged["shap_rank"]

    print()
    print("  biggest disagreements between SHAP and gain importance:")
    print()
    moved = merged.reindex(merged["moved"].abs().sort_values(
        ascending=False).index).head(8)
    print(moved[["feature", "shap_rank", "gain_rank", "moved"]]
          .to_string(index=False))
    print()
    print("  Gain splits credit arbitrarily between correlated features;")
    print("  SHAP attributes each row to the feature that actually moved")
    print("  that prediction. Where they disagree, trust SHAP.")

    # ---- 3. the collusion shortcut, settled -----------------------------
    print()
    print(LINE)
    print("3. COLLUSION SHORTCUT CHECK (open since Task 10)")
    print(LINE)
    watch = ["merchant_txn_count", "merchant_card_count_7d",
             "merchant_amount_mean", "merchant_is_online"]
    print()
    for w in watch:
        row = merged[merged["feature"] == w]
        if len(row):
            r = row.iloc[0]
            print(f"  {w:<26} SHAP rank {int(r['shap_rank']):>3}  "
                  f"{r['pct']:>6.2f}% of |SHAP|")
        else:
            print(f"  {w:<26} not in the model")
    print()
    print("  Task 10 warned the model might learn 'low-volume merchant'")
    print("  instead of 'inflated amounts'. High SHAP on volume features")
    print("  would confirm that shortcut.")

    # ---- 4. worked examples ---------------------------------------------
    print()
    print(LINE)
    print("4. WORKED EXAMPLES - what an analyst would see")
    print(LINE)

    scores = np.asarray(booster.predict(X), dtype=float)
    payload_examples = []

    patterns = sorted(ft[y].dropna().unique()) if ft is not None else [None]
    for pat in patterns[:examples]:
        if pat is None:
            idx = int(np.argsort(scores)[-1])
        else:
            mask = y & (ft == pat).to_numpy()
            if not mask.any():
                continue
            cand = np.flatnonzero(mask)
            idx = int(cand[np.argmax(scores[cand])])

        e = explainer.explain_one(X, idx, top=5)
        print()
        print(f"  --- {pat or 'highest-scoring row'} ---")
        print(f"  score {e.prediction:.5f}   "
              f"(base rate {1 / (1 + np.exp(-e.base_value)):.5f})")
        print()
        print("  pushed TOWARD fraud:")
        for f, val, sv in e.top_positive:
            print(f"      {f:<28} = {val:>12,.2f}   SHAP {sv:+.4f}")
        print()
        print("  pushed AWAY from fraud:")
        for f, val, sv in e.top_negative:
            print(f"      {f:<28} = {val:>12,.2f}   SHAP {sv:+.4f}")
        print()
        print(f"  analyst summary: {e.sentence()}")

        payload_examples.append({"pattern": str(pat), **e.to_dict()})

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / f"task18_shap_{tag}.json"
    out.write_text(json.dumps({
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "tag": tag,
        "additivity": v,
        "global_importance": merged.to_dict(orient="records"),
        "examples": payload_examples,
    }, indent=2, default=float), encoding="utf-8")

    print()
    print(LINE)
    print(f"  saved: {out}")
    print(LINE)


if __name__ == "__main__":
    app()