"""
scripts/test_novel_fraud.py

Task 17.3 - THE REAL EXPERIMENT.

Remove one fraud pattern entirely from LightGBM's training data, then
measure who catches it in validation. That pattern is, from the
supervised model's point of view, an attack invented after deployment.

Run once per pattern. A supervised model should collapse on the
pattern it never saw; an unsupervised detector should not care, because
it never used labels in the first place.

    python scripts/test_novel_fraud.py
    python scripts/test_novel_fraud.py --patterns account_takeover
"""

from __future__ import annotations

import json
from datetime import datetime

import lightgbm as lgb
import numpy as np
import pandas as pd
import typer
from sklearn.metrics import average_precision_score

from streamguard.ml.splitter import split, PROJECT_ROOT
from streamguard.ml.tuning import final_params
from streamguard.ml.anomaly import (
    IsolationForestDetector, MahalanobisDetector, AnomalyConfig, fit_on_normal,
)
from streamguard.utils.logging_config import get_logger, setup_logging

app = typer.Typer(add_completion=False)
log = get_logger(__name__)

REPORTS_DIR = PROJECT_ROOT / "reports"
LINE = "=" * 72


def recall_at_k(y_true: np.ndarray, scores: np.ndarray,
                mask: np.ndarray, k: int) -> tuple[float, int, int]:
    """Recall for one subgroup within the top k overall."""
    k = min(int(k), len(scores))
    top = np.argsort(scores, kind="stable")[-k:]
    flagged = np.zeros(len(scores), dtype=bool)
    flagged[top] = True
    n = int(mask.sum())
    caught = int((flagged & mask).sum())
    return (caught / n if n else 0.0), caught, n


@app.command()
def main(
    patterns: str = typer.Option(
        "", help="Comma-separated. Empty = every pattern."),
    alerts_per_day: int = typer.Option(100),
    n_jobs: int = typer.Option(6),
) -> None:
    setup_logging()
    print(LINE)
    print("TASK 17.3 - CAN WE CATCH FRAUD WE NEVER TRAINED ON?")
    print(LINE)

    blocks = split(save_manifest=False)
    train, val = blocks["train"], blocks["val"]
    val_days = val.day_range[1] - val.day_range[0] + 1
    k = alerts_per_day * val_days

    if "fraud_type" not in train.meta.columns:
        print("ERROR: fraud_type not in metadata.")
        raise typer.Exit(1)

    tr_ft = train.meta["fraud_type"].reset_index(drop=True)
    val_ft = val.meta["fraud_type"].reset_index(drop=True)
    tr_fraud = np.asarray(train.y).astype(bool)
    val_fraud = np.asarray(val.y).astype(bool)

    all_patterns = sorted(tr_ft[tr_fraud].dropna().unique())
    chosen = ([p.strip() for p in patterns.split(",") if p.strip()]
              if patterns else all_patterns)

    print()
    print(f"  patterns to test: {', '.join(chosen)}")
    print(f"  k = {k:,} ({alerts_per_day}/day x {val_days} days)")
    print()
    print("  For each pattern: retrain LightGBM with that pattern's rows")
    print("  REMOVED from training, then measure recall on it in")
    print("  validation. The detectors are unchanged - they never used")
    print("  labels, so there is nothing to remove.")

    # ---- fit the detectors once (labels only select normal rows) ------
    cfg = AnomalyConfig(n_jobs=n_jobs)
    print()
    print(LINE)
    print("FITTING DETECTORS (normal training rows only)")
    print(LINE)
    iso = fit_on_normal(IsolationForestDetector(cfg), train.X, train.y)
    maha = fit_on_normal(MahalanobisDetector(cfg), train.X, train.y)
    iso_scores = iso.score_samples(val.X)
    maha_scores = maha.score_samples(val.X)

    tuning_file = REPORTS_DIR / "task14_tuning.json"
    best = json.loads(tuning_file.read_text(encoding="utf-8"))["best_params"] \
        if tuning_file.exists() else {}
    params = final_params(best, n_jobs=n_jobs)

    rows = []
    for pat in chosen:
        print()
        print(LINE)
        print(f"  HELD OUT: {pat}")
        print(LINE)

        drop = tr_fraud & (tr_ft == pat).to_numpy()
        keep = ~drop
        n_dropped = int(drop.sum())

        X_tr = train.X.loc[keep]
        y_tr = np.asarray(train.y)[keep]

        print(f"  removed {n_dropped:,} {pat} rows from training "
              f"({len(X_tr):,} rows left, {int(y_tr.sum()):,} fraud)")

        clf = lgb.LGBMClassifier(**params)
        clf.fit(X_tr, y_tr,
                eval_set=[(val.X, val.y)], eval_names=["val"],
                callbacks=[lgb.early_stopping(100, verbose=False)])
        sup_scores = np.asarray(clf.booster_.predict(val.X), dtype=float)

        pat_mask = val_fraud & (val_ft == pat).to_numpy()
        n_val = int(pat_mask.sum())
        if n_val == 0:
            print(f"  no {pat} rows in validation - skipping")
            continue

        sup_r, sup_c, _ = recall_at_k(val.y, sup_scores, pat_mask, k)
        iso_r, iso_c, _ = recall_at_k(val.y, iso_scores, pat_mask, k)
        mah_r, mah_c, _ = recall_at_k(val.y, maha_scores, pat_mask, k)

        # Overall PR-AUC of the crippled supervised model, for context.
        sup_ap = float(average_precision_score(val.y, sup_scores))

        print()
        print(f"  recall on {n_val} held-out {pat} rows, in the top {k:,}:")
        print()
        print(f"    lightgbm (never saw it)   {sup_r * 100:>6.1f}%   "
              f"({sup_c} of {n_val})")
        print(f"    isolation_forest          {iso_r * 100:>6.1f}%   "
              f"({iso_c} of {n_val})")
        print(f"    mahalanobis               {mah_r * 100:>6.1f}%   "
              f"({mah_c} of {n_val})")
        print()
        print(f"    crippled lightgbm overall PR-AUC: {sup_ap:.4f}")

        best_unsup = max(iso_r, mah_r)
        if best_unsup > sup_r + 0.05:
            print()
            print("    UNSUPERVISED WINS. A detector that never saw a label")
            print("    beat the supervised model on a pattern it was never")
            print("    trained on. This is the case for running both.")
        elif sup_r > best_unsup + 0.05:
            print()
            print("    SUPERVISED STILL WINS despite never seeing this")
            print("    pattern - it generalised from the others, probably")
            print("    through shared features.")
        else:
            print()
            print("    Too close to call at this sample size.")

        rows.append({
            "pattern": pat,
            "n_train_removed": n_dropped,
            "n_val": n_val,
            "supervised_recall": sup_r,
            "isolation_recall": iso_r,
            "mahalanobis_recall": mah_r,
            "supervised_pr_auc": sup_ap,
        })

    # ---- summary -------------------------------------------------------
    print()
    print(LINE)
    print("SUMMARY - recall on the HELD-OUT pattern")
    print(LINE)
    print()
    print(f"  {'pattern':<22}{'n':>5}{'lightgbm':>11}"
          f"{'isolation':>11}{'mahalanobis':>13}")
    print("  " + "-" * 62)
    for r in rows:
        print(f"  {r['pattern']:<22}{r['n_val']:>5}"
              f"{r['supervised_recall'] * 100:>10.1f}%"
              f"{r['isolation_recall'] * 100:>10.1f}%"
              f"{r['mahalanobis_recall'] * 100:>12.1f}%")

    print()
    print("  Patterns where lightgbm collapses but a detector holds up")
    print("  are the argument for running both in production.")
    print("  Patterns where lightgbm holds up anyway mean it generalised")
    print("  from shared features - also worth knowing.")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / "task17_novel_fraud.json"
    out.write_text(json.dumps({
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "k": k,
        "block": "validation",
        "results": rows,
    }, indent=2), encoding="utf-8")
    print()
    print(f"  saved: {out}")
    print(LINE)


if __name__ == "__main__":
    app()