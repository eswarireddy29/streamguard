"""
scripts/diagnose_baseline.py

Task 12.5b - explain the logistic baseline's PR-AUC.

Answers three questions:
  1. Which single features, alone, separate fraud from normal?
  2. Is any feature a PERFECT separator (ranges never overlap)?
  3. How much of the score survives when the strongest are removed?

Read-only with respect to data. Touches TRAIN and VALIDATION only.

    python scripts/diagnose_baseline.py
    python scripts/diagnose_baseline.py --ablation-steps 5
    python scripts/diagnose_baseline.py --sample 200000
"""

from __future__ import annotations

import json
from datetime import datetime

import numpy as np
import pandas as pd
import typer
from sklearn.metrics import average_precision_score

from streamguard.ml.splitter import split, PROJECT_ROOT
from streamguard.ml.baselines import LogisticBaseline
from streamguard.ml.metrics import evaluate, format_result
from streamguard.utils.logging_config import get_logger, setup_logging

app = typer.Typer(add_completion=False)
log = get_logger(__name__)

REPORTS_DIR = PROJECT_ROOT / "reports"
LINE = "=" * 72


def single_feature_ap(X: pd.DataFrame, y: np.ndarray) -> pd.DataFrame:
    """PR-AUC of each feature used alone as the score.

    A feature can point either way (high = fraud, or low = fraud), so
    we score it and its negation and keep the better one, recording
    which direction won.
    """
    rows = []
    yv = np.asarray(y).astype(int)
    for col in X.columns:
        x = X[col].to_numpy(dtype=float)
        if not np.isfinite(x).all():
            x = np.nan_to_num(x, nan=0.0, posinf=0.0, neginf=0.0)
        ap_pos = average_precision_score(yv, x)
        ap_neg = average_precision_score(yv, -x)
        if ap_pos >= ap_neg:
            ap, direction = ap_pos, "high=fraud"
        else:
            ap, direction = ap_neg, "low=fraud"
        rows.append({"feature": col, "ap_alone": ap, "direction": direction})
    return (pd.DataFrame(rows)
            .sort_values("ap_alone", ascending=False)
            .reset_index(drop=True))


def separator_report(X: pd.DataFrame, y: np.ndarray) -> pd.DataFrame:
    """Per feature: fraud vs normal means, and overlap of their ranges.

    'perfect' means the two groups' value ranges do not overlap at all.
    A perfect separator is either a generator artefact or leakage; you
    need to know which one, by name.
    """
    yv = np.asarray(y).astype(bool)
    rows = []
    for col in X.columns:
        x = X[col].to_numpy(dtype=float)
        x = np.nan_to_num(x, nan=0.0, posinf=0.0, neginf=0.0)
        f, n = x[yv], x[~yv]
        if len(f) == 0 or len(n) == 0:
            continue
        perfect = (f.min() > n.max()) or (f.max() < n.min())
        rows.append({
            "feature": col,
            "normal_mean": n.mean(),
            "fraud_mean": f.mean(),
            "normal_max": n.max(),
            "fraud_min": f.min(),
            "perfect_separator": perfect,
        })
    return pd.DataFrame(rows)


@app.command()
def main(
    ablation_steps: int = typer.Option(4, help="How many drop-rounds to run"),
    drop_per_step: int = typer.Option(3, help="Features removed each round"),
    sample: int = typer.Option(0, help="Subsample training rows (0 = all)"),
    alerts_per_day: int = typer.Option(100),
) -> None:
    setup_logging()
    print(LINE)
    print("TASK 12.5b - BASELINE DIAGNOSTIC")
    print(LINE)

    blocks = split(save_manifest=False)
    train, val = blocks["train"], blocks["val"]
    val_days = val.day_range[1] - val.day_range[0] + 1
    ft = val.meta["fraud_type"] if "fraud_type" in val.meta.columns else None

    Xtr, ytr = train.X, train.y
    if sample and sample < len(Xtr):
        # Stratified-ish subsample: keep ALL fraud, sample the normals.
        # Dropping fraud would change the problem; dropping normals only
        # changes how many easy negatives the model sees.
        idx_f = np.flatnonzero(ytr == 1)
        idx_n = np.flatnonzero(ytr == 0)
        rng = np.random.default_rng(42)
        keep_n = rng.choice(idx_n, size=max(0, sample - len(idx_f)), replace=False)
        keep = np.sort(np.concatenate([idx_f, keep_n]))
        Xtr, ytr = Xtr.iloc[keep], ytr[keep]
        print(f"  subsampled train to {len(Xtr):,} rows ({int(ytr.sum()):,} fraud)")

    print()
    print(train.describe())
    print(val.describe())

    # ---- 1. single-feature power ------------------------------------
    print()
    print(LINE)
    print("1. SINGLE-FEATURE PR-AUC  (validation, no model fitted)")
    print(LINE)
    print(f"  random = {val.prevalence:.4f}")
    print()
    sf = single_feature_ap(val.X, val.y)
    print("  strongest 15 features used ALONE:")
    print(sf.head(15).to_string(index=False,
                                formatters={"ap_alone": "{:.4f}".format}))
    print()
    print("  weakest 5:")
    print(sf.tail(5).to_string(index=False,
                               formatters={"ap_alone": "{:.4f}".format}))

    # ---- 2. perfect separators --------------------------------------
    print()
    print(LINE)
    print("2. PERFECT SEPARATORS  (value ranges that never overlap)")
    print(LINE)
    sep = separator_report(val.X, val.y)
    perfect = sep[sep["perfect_separator"]]
    if len(perfect) == 0:
        print("  none - no feature fully separates the two classes.")
    else:
        print(f"  {len(perfect)} found. Each is a giveaway the model can")
        print("  exploit. Confirm whether it is a generator artefact:")
        print()
        print(perfect.to_string(index=False, float_format=lambda v: f"{v:,.4f}"))

    # ---- 3. ablation -------------------------------------------------
    print()
    print(LINE)
    print("3. ABLATION  (refit after removing the strongest features)")
    print(LINE)
    print("  If the score collapses, the model rides a few giveaways.")
    print("  If it holds up, the signal is spread across the features.")
    print()

    order = list(sf["feature"])
    dropped: list[str] = []
    ablation = []

    for step in range(ablation_steps + 1):
        cols = [c for c in train.X.columns if c not in set(dropped)]
        if len(cols) < 5:
            print("  stopping - fewer than 5 features left")
            break
        model = LogisticBaseline().fit(Xtr[cols], ytr)
        scores = model.score_samples(val.X[cols])
        ap = float(average_precision_score(val.y, scores))
        ablation.append({"step": step, "n_features": len(cols),
                         "dropped_so_far": list(dropped), "pr_auc": ap})
        label = "none (full model)" if not dropped else ", ".join(dropped[-drop_per_step:])
        print(f"  step {step}: {len(cols):>2} features, PR-AUC {ap:.4f}   "
              f"last dropped: {label}")
        if step == 0:
            full_ap = ap
            full_scores = scores
        dropped += [c for c in order if c not in set(dropped)][:drop_per_step]

    # ---- 4. per-pattern recall of the full model ---------------------
    print()
    print(LINE)
    print("4. FULL MODEL, PER-PATTERN RECALL")
    print(LINE)
    r = evaluate("logistic_regression", "val", val.y, full_scores, ft,
                 val_days, alerts_per_day)
    print(format_result(r))

    # ---- 5. verdict prompts -----------------------------------------
    print()
    print(LINE)
    print("HOW TO READ THIS")
    print(LINE)
    top_ap = sf.iloc[0]
    print(f"  Strongest single feature: {top_ap['feature']} "
          f"(PR-AUC {top_ap['ap_alone']:.4f} alone)")
    print(f"  Full model PR-AUC: {full_ap:.4f}")
    if len(ablation) > 1:
        last = ablation[-1]
        print(f"  After dropping {len(last['dropped_so_far'])} features: "
              f"{last['pr_auc']:.4f}")
    print()
    print("  Collapse after a few drops  -> a handful of giveaways carry it.")
    print("  Score holds up              -> signal is genuinely distributed.")
    print("  A perfect separator listed  -> name it in the README as a")
    print("                                 synthetic-data limitation.")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / "task12_diagnostic.json"
    out.write_text(json.dumps({
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "val_prevalence": val.prevalence,
        "single_feature_ap": sf.to_dict(orient="records"),
        "perfect_separators": perfect["feature"].tolist(),
        "ablation": ablation,
        "full_model": r.to_dict(),
    }, indent=2), encoding="utf-8")
    print()
    print(f"  saved: {out}")
    print(LINE)


if __name__ == "__main__":
    app()