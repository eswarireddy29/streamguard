"""
scripts/train_final.py

Task 14.4 - train the model with the tuned hyperparameters.

Reads the winner from reports/task14_tuning.json, retrains, evaluates
on VALIDATION, and saves. Test is never loaded.

    python scripts/train_final.py
    python scripts/train_final.py --tag v4
"""

from __future__ import annotations

import json
from datetime import datetime

import lightgbm as lgb
import typer
from sklearn.metrics import average_precision_score

from streamguard.ml.splitter import split, PROJECT_ROOT
from streamguard.ml.lgbm import LGBMModel
from streamguard.ml.tuning import final_params
from streamguard.ml.metrics import evaluate, format_result, comparison_table
from streamguard.utils.logging_config import get_logger, setup_logging

app = typer.Typer(add_completion=False)
log = get_logger(__name__)

REPORTS_DIR = PROJECT_ROOT / "reports"
MODELS_DIR = PROJECT_ROOT / "models"
LINE = "=" * 72


@app.command()
def main(
    tag: str = typer.Option("v4"),
    n_jobs: int = typer.Option(6),
    alerts_per_day: int = typer.Option(100),
) -> None:
    setup_logging()
    print(LINE)
    print("TASK 14.4 - FINAL TUNED MODEL")
    print(LINE)

    tuning_file = REPORTS_DIR / "task14_tuning.json"
    if not tuning_file.exists():
        print(f"ERROR: {tuning_file} not found. Run scripts/tune_lgbm.py first.")
        raise typer.Exit(1)

    tuned = json.loads(tuning_file.read_text(encoding="utf-8"))
    best = tuned["best_params"]

    blocks = split(save_manifest=False)
    train, val = blocks["train"], blocks["val"]
    val_days = val.day_range[1] - val.day_range[0] + 1
    ft = val.meta["fraud_type"] if "fraud_type" in val.meta.columns else None

    print()
    print(train.describe())
    print(val.describe())
    print()
    print("  tuned hyperparameters (Task 14.3):")
    for k, v in sorted(best.items()):
        print(f"    {k:<22} {v}")

    params = final_params(best, n_jobs=n_jobs)
    print()
    print(f"  is_unbalance = {params['is_unbalance']}  (Task 14.1)")
    print()
    print(LINE)
    print("TRAINING")
    print(LINE)

    clf = lgb.LGBMClassifier(**params)
    clf.fit(
        train.X, train.y,
        eval_set=[(train.X, train.y), (val.X, val.y)],
        eval_names=["train", "val"],
        callbacks=[lgb.early_stopping(100, verbose=False),
                   lgb.log_evaluation(period=50)],
    )

    model = LGBMModel()
    model.model = clf
    model.feature_names = list(train.X.columns)

    scores = model.score_samples(val.X)
    r = evaluate("lightgbm_tuned", "val", val.y, scores, ft,
                 val_days, alerts_per_day,
                 binary_pred=model.predict(val.X),
                 notes=["is_unbalance=False - probabilities ARE calibrated"])

    train_ap = float(average_precision_score(
        train.y, model.score_samples(train.X)))
    gap = train_ap - r.pr_auc

    print()
    print(LINE)
    print("1. TUNED MODEL ON VALIDATION")
    print(LINE)
    print(format_result(r))
    print()
    print(f"  trees        {clf.best_iteration_}")
    print(f"  train PR-AUC {train_ap:.4f}")
    print(f"  gap          {gap:.4f}")

    print()
    print(LINE)
    print("2. PROGRESS ACROSS TASKS")
    print(LINE)
    print(f"  {'stage':<34}{'PR-AUC':>9}{'gap':>9}{'trees':>8}")
    print("  " + "-" * 60)
    print(f"  {'Task 13 (is_unbalance=True)':<34}{0.9201:>9.4f}"
          f"{0.0799:>9.4f}{1399:>8}")
    print(f"  {'Task 14.1 (is_unbalance=False)':<34}{0.9495:>9.4f}"
          f"{0.0458:>9.4f}{116:>8}")
    print(f"  {'Task 14.4 (tuned)':<34}{r.pr_auc:>9.4f}"
          f"{gap:>9.4f}{clf.best_iteration_:>8}")

    print()
    print(LINE)
    print("3. FEATURE IMPORTANCE (top 10 by gain)")
    print(LINE)
    print()
    print(model.importance("gain").head(10).to_string(
        index=False, formatters={"gain": "{:,.0f}".format,
                                 "pct": "{:.2f}".format}))

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    model_path = MODELS_DIR / f"lgbm_{tag}.txt"
    clf.booster_.save_model(str(model_path), num_iteration=clf.best_iteration_)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / f"task14_final_{tag}.json"
    out.write_text(json.dumps({
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "tag": tag,
        "params": {k: v for k, v in params.items()},
        "block": "validation",
        "random_pr_auc": val.prevalence,
        "result": r.to_dict(),
        "train_pr_auc": train_ap,
        "gap": gap,
        "best_iteration": int(clf.best_iteration_ or 0),
    }, indent=2), encoding="utf-8")

    print()
    print(LINE)
    print(f"  model   : {model_path}")
    print(f"  results : {out}")
    print(LINE)


if __name__ == "__main__":
    app()