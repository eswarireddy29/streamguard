"""
scripts/tune_lgbm.py

Task 14.3 - run the random hyperparameter search.

    python scripts/tune_lgbm.py
    python scripts/tune_lgbm.py --n-trials 50
    python scripts/tune_lgbm.py --n-trials 10     # quick check first

Test is never loaded. Validation drives every decision.
"""

from __future__ import annotations

import json
from datetime import datetime

import typer

from streamguard.ml.splitter import split, PROJECT_ROOT
from streamguard.ml.tuning import random_search, SEARCH_SPACE, FIXED
from streamguard.utils.logging_config import get_logger, setup_logging

app = typer.Typer(add_completion=False)
log = get_logger(__name__)

REPORTS_DIR = PROJECT_ROOT / "reports"
LINE = "=" * 72

# Task 14.1, is_unbalance=False, default hyperparameters.
BASELINE_PR_AUC = 0.9495
BASELINE_GAP = 0.0458


@app.command()
def main(
    n_trials: int = typer.Option(30, help="How many combinations to try"),
    n_jobs: int = typer.Option(6),
    seed: int = typer.Option(42),
) -> None:
    setup_logging()
    print(LINE)
    print("TASK 14.3 - HYPERPARAMETER SEARCH")
    print(LINE)

    blocks = split(save_manifest=False)
    train, val = blocks["train"], blocks["val"]

    print()
    print(train.describe())
    print(val.describe())
    print()
    print(f"  baseline to beat: PR-AUC {BASELINE_PR_AUC:.4f}, "
          f"gap {BASELINE_GAP:.4f}")
    print(f"  trials: {n_trials}   searching {len(SEARCH_SPACE)} settings")
    print(f"  is_unbalance = {FIXED['is_unbalance']}  (decided at Task 14.1)")
    print()
    print("  Each trial trains on TRAIN and is scored on VALIDATION.")
    print("  Expect roughly 1-4 minutes per trial.")
    print()
    print(LINE)

    def progress(t, result):
        marker = ""
        if t.pr_auc >= result.best_pr_auc:
            marker = "  <-- best so far"
        print(t.line() + marker)

    result = random_search(
        train.X, train.y, val.X, val.y,
        n_trials=n_trials, n_jobs=n_jobs, seed=seed,
        baseline_pr_auc=BASELINE_PR_AUC, baseline_gap=BASELINE_GAP,
        on_trial=progress,
    )

    print()
    print(LINE)
    print(f"TOP 10 OF {n_trials} TRIALS")
    print(LINE)
    print(result.table(10))

    print()
    print(LINE)
    print("WINNER")
    print(LINE)
    print(f"  PR-AUC   {result.best_pr_auc:.4f}   "
          f"(baseline {BASELINE_PR_AUC:.4f}, "
          f"{result.best_pr_auc - BASELINE_PR_AUC:+.4f})")
    print(f"  gap      {result.best_gap:.4f}   "
          f"(baseline {BASELINE_GAP:.4f}, "
          f"{result.best_gap - BASELINE_GAP:+.4f})")
    print(f"  trees    {result.best_iteration}")
    print()
    for k, v in sorted(result.best_params.items()):
        print(f"    {k:<22} {v}")
    print()
    print(f"  total search time: {result.total_seconds / 60:.1f} minutes")
    print()
    if result.best_pr_auc <= BASELINE_PR_AUC:
        print("  NOTE: the search did not beat the default settings.")
        print("  That is a legitimate result - the defaults were already")
        print("  reasonable. Keep them and say so in the report.")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / "task14_tuning.json"
    result.save(out)
    print(f"  saved: {out}")
    print(LINE)


if __name__ == "__main__":
    app()