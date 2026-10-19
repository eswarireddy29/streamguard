"""
scripts/compare_imbalance.py

Task 14.1 - compare four ways of handling 0.368% fraud.

Each is trained on TRAIN and judged on VALIDATION. Test is untouched.

    python scripts/compare_imbalance.py
"""

from __future__ import annotations

import json
from datetime import datetime

import numpy as np
import typer
from sklearn.metrics import average_precision_score

from streamguard.ml.splitter import split, PROJECT_ROOT
from streamguard.ml.lgbm import LGBMModel, LGBMConfig
from streamguard.ml.metrics import evaluate, format_result
from streamguard.utils.logging_config import get_logger, setup_logging

app = typer.Typer(add_completion=False)
log = get_logger(__name__)

REPORTS_DIR = PROJECT_ROOT / "reports"
LINE = "=" * 72


def undersample(X, y, ratio: int, seed: int = 42):
    """Keep ALL fraud, keep `ratio` normals per fraud row.

    Dropping fraud would change the problem. Dropping normals only
    changes how many easy negatives the model sees.
    """
    y = np.asarray(y)
    idx_f = np.flatnonzero(y == 1)
    idx_n = np.flatnonzero(y == 0)
    keep_n = min(len(idx_n), len(idx_f) * ratio)
    rng = np.random.default_rng(seed)
    sampled = rng.choice(idx_n, size=keep_n, replace=False)
    keep = np.sort(np.concatenate([idx_f, sampled]))
    return X.iloc[keep], y[keep]


@app.command()
def main(
    n_estimators: int = typer.Option(600, help="Fewer trees - this is a comparison"),
    n_jobs: int = typer.Option(6),
    alerts_per_day: int = typer.Option(100),
    undersample_ratio: int = typer.Option(50, help="Normals kept per fraud row"),
) -> None:
    setup_logging()
    print(LINE)
    print("TASK 14.1 - IMBALANCE STRATEGIES")
    print(LINE)

    blocks = split(save_manifest=False)
    train, val = blocks["train"], blocks["val"]
    val_days = val.day_range[1] - val.day_range[0] + 1
    ft = val.meta["fraud_type"] if "fraud_type" in val.meta.columns else None

    n_fraud = int(train.y.sum())
    n_normal = len(train.y) - n_fraud
    pos_weight = n_normal / n_fraud

    print()
    print(train.describe())
    print(val.describe())
    print()
    print(f"  normal / fraud ratio in train = {pos_weight:.1f}")
    print(f"  random PR-AUC on validation   = {val.prevalence:.4f}")
    print(f"  Task 13 result (is_unbalance) = 0.9201")

    strategies = [
        ("none", dict(is_unbalance=False), None),
        ("is_unbalance", dict(is_unbalance=True), None),
        ("scale_pos_weight", dict(is_unbalance=False,
                                  scale_pos_weight=pos_weight), None),
        (f"undersample_1:{undersample_ratio}", dict(is_unbalance=True),
         undersample_ratio),
    ]

    results = []
    for name, overrides, ratio in strategies:
        print()
        print(LINE)
        print(f"  {name}")
        print(LINE)

        Xtr, ytr = train.X, train.y
        if ratio is not None:
            Xtr, ytr = undersample(Xtr, ytr, ratio)
            print(f"  training rows: {len(Xtr):,} "
                  f"({int(ytr.sum()):,} fraud, {ytr.mean() * 100:.2f}%)")

        spw = overrides.pop("scale_pos_weight", None)
        cfg = LGBMConfig(n_estimators=n_estimators, n_jobs=n_jobs, **overrides)
        params = cfg.to_params()
        if spw is not None:
            params["scale_pos_weight"] = spw

        model = LGBMModel(cfg)
        import lightgbm as lgb
        model.feature_names = list(Xtr.columns)
        model.model = lgb.LGBMClassifier(**params)
        model.model.fit(
            Xtr, ytr,
            eval_set=[(val.X, val.y)],
            eval_names=["val"],
            callbacks=[lgb.early_stopping(100, verbose=False)],
        )

        scores = model.score_samples(val.X)
        r = evaluate(name, "val", val.y, scores, ft, val_days, alerts_per_day,
                     binary_pred=model.predict(val.X))

        train_ap = float(average_precision_score(
            train.y, model.score_samples(train.X)))
        gap = train_ap - r.pr_auc

        print(format_result(r))
        print()
        print(f"  train PR-AUC {train_ap:.4f}   gap {gap:.4f}   "
              f"trees {model.model.best_iteration_}")

        results.append({"strategy": name, "pr_auc": r.pr_auc,
                        "train_pr_auc": train_ap, "gap": gap,
                        "precision_at_k": r.precision_at_k,
                        "recall_at_k": r.recall_at_k,
                        "per_pattern": r.per_pattern_recall_at_k,
                        "trees": int(model.model.best_iteration_ or 0)})

    print()
    print(LINE)
    print("COMPARISON")
    print(LINE)
    print(f"  {'strategy':<22}{'PR-AUC':>9}{'train':>9}{'gap':>8}"
          f"{'prec@k':>9}{'trees':>8}")
    print("  " + "-" * 63)
    for r in results:
        print(f"  {r['strategy']:<22}{r['pr_auc']:>9.4f}{r['train_pr_auc']:>9.4f}"
              f"{r['gap']:>8.4f}{r['precision_at_k']:>9.4f}{r['trees']:>8}")

    best = max(results, key=lambda r: r["pr_auc"])
    print()
    print(f"  highest PR-AUC: {best['strategy']} ({best['pr_auc']:.4f})")
    print("  A smaller gap with similar PR-AUC is the better model -")
    print("  it is likelier to hold up on the untouched test set.")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / "task14_imbalance.json"
    out.write_text(json.dumps({
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "random_pr_auc": val.prevalence,
        "pos_weight": pos_weight,
        "results": results,
    }, indent=2), encoding="utf-8")
    print()
    print(f"  saved: {out}")
    print(LINE)


if __name__ == "__main__":
    app()