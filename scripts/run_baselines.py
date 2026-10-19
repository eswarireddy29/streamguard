"""
scripts/run_baselines.py

Task 12.5 - fit the three baselines on TRAIN, evaluate on VALIDATION.

The test set is never touched here. Validation is what you tune on.

    python scripts/run_baselines.py
    python scripts/run_baselines.py --alerts-per-day 200
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import typer

from streamguard.ml.splitter import split, PROJECT_ROOT
from streamguard.ml.baselines import (
    AlwaysNegativeBaseline, RuleBaseline, LogisticBaseline,
)
from streamguard.ml.metrics import evaluate, format_result, comparison_table
from streamguard.utils.logging_config import get_logger, setup_logging

app = typer.Typer(add_completion=False)
log = get_logger(__name__)

REPORTS_DIR = PROJECT_ROOT / "reports"
LINE = "=" * 72


@app.command()
def main(
    alerts_per_day: int = typer.Option(100, help="Cases an analyst reviews daily"),
    save: bool = typer.Option(True, help="Write results JSON to reports/"),
) -> None:
    setup_logging()

    print(LINE)
    print("TASK 12 - BASELINE MODELS")
    print(LINE)

    blocks = split()
    train, val = blocks["train"], blocks["val"]

    print()
    print(train.describe())
    print(val.describe())
    print()
    print(f"  features: {train.X.shape[1]}")
    print(f"  train memory: {train.X.memory_usage(deep=True).sum() / 1e6:.0f} MB")
    print()
    print(f"  A random model scores PR-AUC = {val.prevalence:.4f} on validation.")
    print("  Read every number below against that.")

    val_days = val.day_range[1] - val.day_range[0] + 1
    fraud_type = val.meta["fraud_type"] if "fraud_type" in val.meta.columns else None

    results = []

    # ---- Baseline 1 -------------------------------------------------
    print()
    print(LINE)
    m1 = AlwaysNegativeBaseline().fit(train.X, train.y)
    s1 = m1.score_samples(val.X)
    r1 = evaluate(m1.name, "val", val.y, s1, fraud_type, val_days, alerts_per_day,
                  binary_pred=m1.predict(val.X),
                  notes=["every score identical - ranking metrics are degenerate",
                         f"accuracy would be {(1 - val.prevalence) * 100:.2f}% "
                         f"while catching 0 fraud"])
    print(format_result(r1))
    results.append(r1)

    # ---- Baseline 2 -------------------------------------------------
    print()
    print(LINE)
    m2 = RuleBaseline().fit(train.X, train.y)
    s2 = m2.score_samples(val.X)
    r2 = evaluate(m2.name, "val", val.y, s2, fraud_type, val_days, alerts_per_day,
                  binary_pred=m2.predict(val.X),
                  notes=["score is the number of rules fired (0-3); many ties"])
    print(format_result(r2))
    print()
    print("  each rule on its own (validation):")
    print(m2.rule_breakdown(val.X, val.y).to_string(index=False))
    results.append(r2)

    # ---- Baseline 3 -------------------------------------------------
    print()
    print(LINE)
    m3 = LogisticBaseline().fit(train.X, train.y)
    s3 = m3.score_samples(val.X)
    r3 = evaluate(m3.name, "val", val.y, s3, fraud_type, val_days, alerts_per_day,
                  binary_pred=m3.predict(val.X),
                  notes=["class_weight='balanced' - probabilities are NOT calibrated"])
    print(format_result(r3))
    print()
    print("  top 10 coefficients by absolute value:")
    print(m3.coefficients(list(train.X.columns)).head(10).to_string(index=False))
    results.append(r3)

    # ---- Comparison -------------------------------------------------
    print()
    print(LINE)
    print("COMPARISON  (validation, k = {:,} = {} per day x {} days)".format(
        r3.k, alerts_per_day, val_days))
    print(LINE)
    print(comparison_table(results))
    print()
    print(f"  random PR-AUC = {val.prevalence:.4f}")
    print("  Task 13's LightGBM must beat the best number above to justify itself.")

    if save:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        out = REPORTS_DIR / "task12_baselines.json"
        out.write_text(json.dumps({
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "block": "validation",
            "alerts_per_day": alerts_per_day,
            "val_days": val_days,
            "random_pr_auc": val.prevalence,
            "results": [r.to_dict() for r in results],
        }, indent=2), encoding="utf-8")
        print()
        print(f"  saved: {out}")

    print(LINE)


if __name__ == "__main__":
    app()