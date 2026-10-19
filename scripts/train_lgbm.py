"""
scripts/train_lgbm.py

Task 13 - train LightGBM, compare against the Task 12 baselines.

The test set is NOT touched. Validation drives early stopping and
every number printed here.

    python scripts/train_lgbm.py
    python scripts/train_lgbm.py --num-leaves 63 --learning-rate 0.03
"""

from __future__ import annotations

import json
from datetime import datetime

import numpy as np
import typer

from streamguard.ml.splitter import split, PROJECT_ROOT
from streamguard.ml.lgbm import LGBMModel, LGBMConfig
from streamguard.ml.metrics import evaluate, format_result, comparison_table
from streamguard.utils.logging_config import get_logger, setup_logging

app = typer.Typer(add_completion=False)
log = get_logger(__name__)

REPORTS_DIR = PROJECT_ROOT / "reports"
MODELS_DIR = PROJECT_ROOT / "models"
LINE = "=" * 72

# The Task 12.5b result this task is testing against.
# Logistic baseline's geo_impossible recall on the CURRENT (post-13.7)
# data. The old 0.80 came from the leaked generator and is not a valid
# comparison any more.
GEO_BASELINE_RECALL = 0.706


@app.command()
def main(
    num_leaves: int = typer.Option(31),
    learning_rate: float = typer.Option(0.05),
    min_child_samples: int = typer.Option(100),
    n_estimators: int = typer.Option(2000),
    n_jobs: int = typer.Option(6, help="6 of 12 threads - 8 GB RAM"),
    alerts_per_day: int = typer.Option(100),
    tag: str = typer.Option("v1", help="Name for this run's saved files"),
) -> None:
    setup_logging()
    print(LINE)
    print("TASK 13 - LIGHTGBM")
    print(LINE)

    blocks = split(save_manifest=False)
    train, val = blocks["train"], blocks["val"]
    val_days = val.day_range[1] - val.day_range[0] + 1
    ft = val.meta["fraud_type"] if "fraud_type" in val.meta.columns else None

    print()
    print(train.describe())
    print(val.describe())
    print()
    print(f"  random PR-AUC on validation = {val.prevalence:.4f}")
    print(f"  logistic baseline (Task 12)  = 0.7062")
    print(f"  precision@k ceiling          = {val.n_fraud}/"
          f"{alerts_per_day * val_days} = "
          f"{val.n_fraud / (alerts_per_day * val_days):.4f}")
    print()
    print("  THE REAL TEST: geo_impossible recall was 80.0% for the linear")
    print("  model because it cannot use a non-monotonic feature. Trees")
    print("  should beat that. Watch section 3 below.")

    cfg = LGBMConfig(
        num_leaves=num_leaves,
        learning_rate=learning_rate,
        min_child_samples=min_child_samples,
        n_estimators=n_estimators,
        n_jobs=n_jobs,
    )

    print()
    print(LINE)
    print("TRAINING  (early stopping on validation PR-AUC)")
    print(LINE)
    model = LGBMModel(cfg).fit(train.X, train.y, val.X, val.y)
    rec = model.record

    print()
    print(f"  trees built      : {rec.best_iteration:,} of {rec.n_estimators_requested:,}")
    print(f"  stopped early    : {rec.stopped_early}")
    print(f"  training time    : {rec.train_seconds:.1f}s")
    print(f"  lightgbm version : {rec.lightgbm_version}")
    if not rec.stopped_early:
        print()
        print("  !!  Did NOT stop early - it used every tree allowed.")
        print("      The model may still have been improving. Re-run with")
        print("      a higher --n-estimators to find the real stopping point.")

    # ---- evaluation --------------------------------------------------
    print()
    print(LINE)
    print("1. LIGHTGBM ON VALIDATION")
    print(LINE)
    scores = model.score_samples(val.X)
    r = evaluate(model.name, "val", val.y, scores, ft, val_days, alerts_per_day,
                 binary_pred=model.predict(val.X),
                 notes=["is_unbalance=True - probabilities NOT calibrated"])
    print(format_result(r))

    # ---- comparison against Task 12 ----------------------------------
    print()
    print(LINE)
    print("2. AGAINST THE TASK 12 BASELINES")
    print(LINE)
    baseline_file = REPORTS_DIR / "task12_baselines.json"
    rows = []
    if baseline_file.exists():
        prev = json.loads(baseline_file.read_text(encoding="utf-8"))
        for d in prev["results"]:
            rows.append(type(r)(**d))
    rows.append(r)
    print(comparison_table(rows))
    print()
    print(f"  random PR-AUC = {val.prevalence:.4f}")

    # ---- THE PREDICTION TEST -----------------------------------------
    print()
    print(LINE)
    print("3. THE GEO_IMPOSSIBLE PREDICTION")
    print(LINE)
    geo = r.per_pattern_recall_at_k.get("geo_impossible")
    n_geo = r.per_pattern_n.get("geo_impossible", 0)
    if geo is None:
        print("  geo_impossible not present in this block - cannot test.")
    else:
        print(f"  linear model (Task 12.5b) : {GEO_BASELINE_RECALL * 100:.1f}%")
        print(f"  lightgbm                  : {geo * 100:.1f}%   (n={n_geo})")
        print()
        if geo > GEO_BASELINE_RECALL:
            print("  PREDICTION HELD. Trees handled the non-monotonic feature")
            print("  that the linear model could not. This is the specific,")
            print("  explainable reason trees earn their complexity here.")
        elif abs(geo - GEO_BASELINE_RECALL) < 1e-9:
            print("  UNCHANGED. Investigate before accepting: check that")
            print("  implied_speed_kmh is actually being split on (step 13.4).")
        else:
            print("  PREDICTION FAILED. The tree model did WORSE on the")
            print("  pattern it should handle best. Do not proceed to Task 14.")
            print("  Check feature importance in step 13.4 first.")
        print()
        print(f"  NOTE: n={n_geo}, so one fraud is worth "
              f"{100 / n_geo if n_geo else 0:.1f} percentage points.")
        print("  Read this as a direction, not a precise figure.")

    # ---- overfitting check -------------------------------------------
    print()
    print(LINE)
    print("4. OVERFITTING CHECK  (train vs validation)")
    print(LINE)
    train_scores = model.score_samples(train.X)
    r_train = evaluate(model.name, "train", train.y, train_scores, None,
                       train.day_range[1] - train.day_range[0] + 1, alerts_per_day)
    gap = r_train.pr_auc - r.pr_auc
    print(f"  train PR-AUC      {r_train.pr_auc:.4f}")
    print(f"  validation PR-AUC {r.pr_auc:.4f}")
    print(f"  gap               {gap:.4f}")
    print()
    if gap > 0.10:
        print("  !!  Large gap - the model fits training far better than")
        print("      unseen data. Task 14 should reduce capacity:")
        print("      lower --num-leaves, raise --min-child-samples.")
    else:
        print("  Gap is modest. The model is generalising, not memorising.")
    print("  (Some gap is normal and expected - zero gap would be suspicious.)")

    # ---- save ---------------------------------------------------------
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    model_path = model.save(MODELS_DIR / f"lgbm_{tag}.txt")
    rec_path = rec.save(MODELS_DIR / f"lgbm_{tag}_training.json")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / f"task13_lgbm_{tag}.json"
    out.write_text(json.dumps({
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "tag": tag,
        "block": "validation",
        "random_pr_auc": val.prevalence,
        "logistic_baseline_pr_auc": 0.9299,
        "geo_impossible_linear_recall": GEO_BASELINE_RECALL,
        "result": r.to_dict(),
        "train_pr_auc": r_train.pr_auc,
        "overfit_gap": gap,
        "best_iteration": rec.best_iteration,
        "stopped_early": rec.stopped_early,
    }, indent=2), encoding="utf-8")

    print()
    print(LINE)
    print(f"  model    : {model_path}")
    print(f"  training : {rec_path}")
    print(f"  results  : {out}")
    print(LINE)


if __name__ == "__main__":
    app()