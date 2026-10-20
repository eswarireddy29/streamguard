"""
scripts/check_calibration.py

Task 15.2 - calibration of the tuned model, on VALIDATION.

Run this BEFORE opening the test set. If calibration is poor, it is
fixed here - on validation - not after seeing test results.

    python scripts/check_calibration.py
    python scripts/check_calibration.py --tag v4 --n-bins 15
"""

from __future__ import annotations

import json
from datetime import datetime

import typer

from streamguard.ml.splitter import split, PROJECT_ROOT
from streamguard.ml.lgbm import LGBMModel
from streamguard.ml.calibration import (
    evaluate_calibration, format_calibration, verdict,
)
from streamguard.utils.logging_config import get_logger, setup_logging

app = typer.Typer(add_completion=False)
log = get_logger(__name__)

MODELS_DIR = PROJECT_ROOT / "models"
REPORTS_DIR = PROJECT_ROOT / "reports"
LINE = "=" * 72


@app.command()
def main(
    tag: str = typer.Option("v4"),
    n_bins: int = typer.Option(10),
) -> None:
    setup_logging()
    model_path = MODELS_DIR / f"lgbm_{tag}.txt"
    if not model_path.exists():
        print(f"ERROR: {model_path} not found. Run scripts/train_final.py first.")
        raise typer.Exit(1)

    print(LINE)
    print(f"TASK 15.2 - CALIBRATION ON VALIDATION  ({model_path.name})")
    print(LINE)

    blocks = split(save_manifest=False)
    val = blocks["val"]

    model = LGBMModel.load(model_path)
    scores = model.score_samples(val.X)

    r = evaluate_calibration(val.y, scores, n_bins=n_bins)

    print()
    print(format_calibration(r))
    print()
    print(LINE)
    print("READING")
    print(LINE)
    print(verdict(r))
    print()
    print("  Task 14.1 set is_unbalance=False, which should give")
    print("  calibrated output. This measures whether it did.")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / f"task15_calibration_val_{tag}.json"
    out.write_text(json.dumps({
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "tag": tag,
        "block": "validation",
        "calibration": r.to_dict(),
    }, indent=2), encoding="utf-8")
    print()
    print(f"  saved: {out}")
    print(LINE)


if __name__ == "__main__":
    app()