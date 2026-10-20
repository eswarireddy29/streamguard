"""
scripts/run_anomaly.py

Task 17.2 - how well do unsupervised detectors do on KNOWN fraud?

This is the weaker test. Both detectors are expected to score far below
LightGBM here, because LightGBM was trained on exactly these patterns.
The point is to establish a floor before the real experiment in 17.3.

    python scripts/run_anomaly.py
"""

from __future__ import annotations

import json
from datetime import datetime

import typer

from streamguard.ml.splitter import split, PROJECT_ROOT
from streamguard.ml.lgbm import LGBMModel
from streamguard.ml.anomaly import (
    IsolationForestDetector, MahalanobisDetector, AnomalyConfig, fit_on_normal,
)
from streamguard.ml.metrics import evaluate, format_result, comparison_table
from streamguard.utils.logging_config import get_logger, setup_logging

app = typer.Typer(add_completion=False)
log = get_logger(__name__)

MODELS_DIR = PROJECT_ROOT / "models"
REPORTS_DIR = PROJECT_ROOT / "reports"
LINE = "=" * 72


@app.command()
def main(
    tag: str = typer.Option("v4"),
    alerts_per_day: int = typer.Option(100),
    n_estimators: int = typer.Option(200),
    max_samples: int = typer.Option(25000),
    n_jobs: int = typer.Option(6),
) -> None:
    setup_logging()
    print(LINE)
    print("TASK 17.2 - UNSUPERVISED DETECTORS ON KNOWN FRAUD")
    print(LINE)

    blocks = split(save_manifest=False)
    train, val = blocks["train"], blocks["val"]
    val_days = val.day_range[1] - val.day_range[0] + 1
    ft = val.meta["fraud_type"] if "fraud_type" in val.meta.columns else None

    print()
    print(train.describe())
    print(val.describe())
    print()
    print("  Detectors are fitted on NORMAL TRAINING ROWS ONLY.")
    print("  Labels select the training rows; they are never a feature.")
    print()
    print("  EXPECT these to score far below LightGBM. LightGBM was")
    print("  trained on exactly these five patterns. The real test is")
    print("  17.3, on a pattern it has never seen.")

    cfg = AnomalyConfig(n_estimators=n_estimators,
                        max_samples=max_samples, n_jobs=n_jobs)

    results = []

    for detector in (IsolationForestDetector(cfg), MahalanobisDetector(cfg)):
        print()
        print(LINE)
        print(f"  {detector.name}")
        print(LINE)

        fit_on_normal(detector, train.X, train.y)
        scores = detector.score_samples(val.X)

        r = evaluate(detector.name, "val", val.y, scores, ft,
                     val_days, alerts_per_day,
                     binary_pred=detector.predict(val.X))
        print()
        print(format_result(r))
        results.append(r)

    # ---- supervised, for contrast -------------------------------------
    model_path = MODELS_DIR / f"lgbm_{tag}.txt"
    if model_path.exists():
        print()
        print(LINE)
        print("  lightgbm (supervised, for contrast)")
        print(LINE)
        model = LGBMModel.load(model_path)
        sup_scores = model.score_samples(val.X)
        r_sup = evaluate("lightgbm", "val", val.y, sup_scores, ft,
                         val_days, alerts_per_day)
        print()
        print(format_result(r_sup))
        results.append(r_sup)

    print()
    print(LINE)
    print("COMPARISON (validation)")
    print(LINE)
    print(comparison_table(results))
    print()
    print(f"  random PR-AUC = {val.prevalence:.4f}")
    print()
    print("  A detector well above random has learned something real")
    print("  about normal behaviour WITHOUT ever seeing a label.")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / "task17_anomaly.json"
    out.write_text(json.dumps({
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "block": "validation",
        "random_pr_auc": val.prevalence,
        "results": [r.to_dict() for r in results],
    }, indent=2), encoding="utf-8")
    print()
    print(f"  saved: {out}")
    print(LINE)


if __name__ == "__main__":
    app()