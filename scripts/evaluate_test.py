"""
scripts/evaluate_test.py

Task 15.3 - FINAL EVALUATION ON THE HELD-OUT TEST SET.

This is the one honest estimate of how the model performs on data no
decision was ever made against. Days 77-90 have not been loaded since
the split was created at Task 12.

NOTHING IS TUNED AFTER THIS. If the test numbers disappoint, that is
the result - going back to tune would destroy the very thing that
makes this estimate meaningful.

    python scripts/evaluate_test.py
"""

from __future__ import annotations

import json
from datetime import datetime

import typer
from sklearn.metrics import average_precision_score

from streamguard.ml.splitter import split, load_test, PROJECT_ROOT
from streamguard.ml.lgbm import LGBMModel
from streamguard.ml.metrics import evaluate, format_result, comparison_table
from streamguard.ml.calibration import (
    evaluate_calibration, format_calibration, verdict,
)
from streamguard.utils.logging_config import get_logger, setup_logging

app = typer.Typer(add_completion=False)
log = get_logger(__name__)

MODELS_DIR = PROJECT_ROOT / "models"
REPORTS_DIR = PROJECT_ROOT / "reports"
LINE = "=" * 72

VAL_PR_AUC = 0.9525
VAL_GAP = 0.0297


@app.command()
def main(
    tag: str = typer.Option("v4"),
    alerts_per_day: int = typer.Option(100),
    n_bins: int = typer.Option(10),
    confirm: bool = typer.Option(
        False, "--confirm",
        help="Required. Opening the test set is a one-time event."),
) -> None:
    setup_logging()

    if not confirm:
        print(LINE)
        print("TASK 15.3 - FINAL TEST SET EVALUATION")
        print(LINE)
        print()
        print("  This opens the HELD-OUT TEST SET (days 77-90).")
        print("  It has not been loaded since Task 12.")
        print()
        print("  Every access is logged to:")
        print("    data/processed/test_set_access.log")
        print()
        print("  A test estimate is only honest while the data is")
        print("  untouched. Each look-then-adjust cycle fits you to it.")
        print()
        print("  Make sure the model is final first:")
        print("    - hyperparameters tuned on VALIDATION   (Task 14.3)")
        print("    - imbalance strategy chosen on VALIDATION (Task 14.1)")
        print("    - calibration checked on VALIDATION     (Task 15.2)")
        print()
        print("  Re-run with --confirm when ready:")
        print("    python scripts/evaluate_test.py --confirm")
        print(LINE)
        raise typer.Exit(0)

    model_path = MODELS_DIR / f"lgbm_{tag}.txt"
    if not model_path.exists():
        print(f"ERROR: {model_path} not found.")
        raise typer.Exit(1)

    print(LINE)
    print(f"TASK 15.3 - FINAL TEST EVALUATION  ({model_path.name})")
    print(LINE)

    blocks = split(save_manifest=False)
    val = blocks["val"]

    test = load_test(
        reason=f"Task 15 final held-out evaluation of lgbm_{tag}"
    )

    model = LGBMModel.load(model_path)
    test_days = test.day_range[1] - test.day_range[0] + 1
    ft = test.meta["fraud_type"] if "fraud_type" in test.meta.columns else None

    print()
    print(val.describe())
    print(test.describe())
    print()
    print(f"  random PR-AUC on test = {test.prevalence:.4f}")
    print(f"  precision@k ceiling   = {test.n_fraud}/"
          f"{alerts_per_day * test_days} = "
          f"{test.n_fraud / (alerts_per_day * test_days):.4f}")

    scores = model.score_samples(test.X)
    r = evaluate("lightgbm_tuned", "test", test.y, scores, ft,
                 test_days, alerts_per_day,
                 binary_pred=(scores >= 0.5).astype(int))

    print()
    print(LINE)
    print("1. TEST SET RESULT")
    print(LINE)
    print(format_result(r))

    # ---- validation vs test -----------------------------------------
    val_scores = model.score_samples(val.X)
    val_ap = float(average_precision_score(val.y, val_scores))
    drop = val_ap - r.pr_auc

    print()
    print(LINE)
    print("2. VALIDATION vs TEST")
    print(LINE)
    print(f"  validation PR-AUC  {val_ap:.4f}")
    print(f"  test PR-AUC        {r.pr_auc:.4f}")
    print(f"  difference         {drop:+.4f}")
    print()
    if abs(drop) < 0.02:
        print("  The two agree closely. The validation estimate was honest -")
        print("  tuning on validation did not inflate it.")
    elif drop > 0:
        print("  Test scores lower than validation. Some of the tuning gain")
        print("  was fitted to validation rather than generalising. The TEST")
        print("  number is the one to report.")
    else:
        print("  Test scores higher than validation. Within normal variation")
        print("  for different time windows; do not read it as improvement.")

    # ---- calibration on test -----------------------------------------
    print()
    print(LINE)
    print("3. CALIBRATION ON TEST")
    print(LINE)
    print()
    cal = evaluate_calibration(test.y, scores, n_bins=n_bins)
    print(format_calibration(cal))
    print()
    print(verdict(cal))

    # ---- full comparison ---------------------------------------------
    print()
    print(LINE)
    print("4. EVERY MODEL, ON TEST")
    print(LINE)
    baseline_file = REPORTS_DIR / "task12_baselines.json"
    rows = []
    if baseline_file.exists():
        prev = json.loads(baseline_file.read_text(encoding="utf-8"))
        print("  (baselines shown are VALIDATION numbers, for reference)")
        for d in prev["results"]:
            rows.append(type(r)(**d))
    rows.append(r)
    print()
    print(comparison_table(rows))

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / f"task15_test_{tag}.json"
    out.write_text(json.dumps({
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "tag": tag,
        "block": "test",
        "test_day_range": list(test.day_range),
        "random_pr_auc": test.prevalence,
        "result": r.to_dict(),
        "validation_pr_auc": val_ap,
        "val_minus_test": drop,
        "calibration": cal.to_dict(),
    }, indent=2), encoding="utf-8")

    print()
    print(LINE)
    print(f"  saved: {out}")
    print()
    print("  THE TEST SET IS NOW USED. Do not tune against these numbers.")
    print(LINE)


if __name__ == "__main__":
    app()