"""
scripts/train_with_graph.py

Task 18A - does adding graph features improve the model?

Trains on features_graph.parquet with the tuned Task 14 hyperparameters
and compares against the 49-feature baseline on the SAME validation
block. Test is not touched.

Two features are dropped as dead:
  ring_size          - 36.78 normal vs 36.38 fraud. Devices are assigned
                       randomly by the generator, so there are no rings
                       to find; the traversal just measures connectivity.
  ring_fraud_density - constant 0.0 by design (filling it from labels
                       would be leakage).

    python scripts/train_with_graph.py
"""

from __future__ import annotations

import json
from datetime import datetime

import lightgbm as lgb
import numpy as np
import pandas as pd
import typer
from sklearn.metrics import average_precision_score

from streamguard.ml.splitter import (
    add_day_index, resolve_column, FORBIDDEN_AS_FEATURES, PROJECT_ROOT,
)
from streamguard.ml.tuning import final_params
from streamguard.ml.metrics import evaluate, format_result, comparison_table
from streamguard.features.computer import FEATURE_NAMES
from streamguard.features.graph import GRAPH_FEATURE_NAMES
from streamguard.utils.logging_config import get_logger, setup_logging

app = typer.Typer(add_completion=False)
log = get_logger(__name__)

PROCESSED = PROJECT_ROOT / "data" / "processed"
REPORTS_DIR = PROJECT_ROOT / "reports"
MODELS_DIR = PROJECT_ROOT / "models"
LINE = "=" * 72

# Features dropped before training, each with a measured reason.
DEAD = ["ring_size", "ring_fraud_density"]

# card_age_days is dropped separately because it is a BASE feature, not
# a graph one. Task 18B found it at SHAP rank 1 (13.54% of mean |SHAP|)
# despite carrying no signal: normal mean 44.10 vs fraud 46.57, same
# std, same 0-90 range. The range is the giveaway - the simulation is
# 90 days long, so this is days-since-simulation-start, a TIME INDEX,
# not card age. The model was splitting on when in the window a
# transaction happened, fitting noise in how 2,034 training frauds
# happened to be distributed across 90 days. Harmless to PR-AUC here;
# would not transfer to real traffic.
DEAD_BASE = ["card_age_days"]

TRAIN_DAYS = 63
VAL_DAYS = 13

BASELINE_PR_AUC = 0.9525   # Task 14.4, 49 features, same validation block


@app.command()
def main(
    tag: str = typer.Option("v5"),
    n_jobs: int = typer.Option(6),
    alerts_per_day: int = typer.Option(100),
) -> None:
    setup_logging()
    print(LINE)
    print("TASK 18A - LIGHTGBM WITH GRAPH FEATURES")
    print(LINE)

    path = PROCESSED / "features_graph.parquet"
    if not path.exists():
        print(f"ERROR: {path} not found. Run build_graph_features.py first.")
        raise typer.Exit(1)

    raw = pd.read_parquet(path)
    df, tcol, aware = add_day_index(raw)
    label_col = resolve_column(df, ["is_fraud", "label", "y"], "fraud label")

    present = set(df.columns)
    base_cols = [c for c in FEATURE_NAMES
                 if c in present and c not in DEAD_BASE]
    graph_cols = [c for c in GRAPH_FEATURE_NAMES
                  if c in present and c not in DEAD]
    all_cols = base_cols + graph_cols

    overlap = set(all_cols) & FORBIDDEN_AS_FEATURES
    if overlap:
        print(f"ERROR: forbidden columns in the feature set: {sorted(overlap)}")
        raise typer.Exit(1)

    print()
    print(f"  base features  {len(base_cols)}  "
          f"(dropped {len(DEAD_BASE)}: {', '.join(DEAD_BASE)})")
    print(f"  graph features {len(graph_cols)}  (dropped {len(DEAD)}: {', '.join(DEAD)})")
    print(f"  total          {len(all_cols)}")

    train_hi = TRAIN_DAYS - 1
    val_hi = train_hi + VAL_DAYS
    tr = df[df["_day"] <= train_hi].sort_values("_local_time", kind="mergesort")
    va = df[(df["_day"] > train_hi) & (df["_day"] <= val_hi)] \
        .sort_values("_local_time", kind="mergesort")

    y_tr = tr[label_col].to_numpy().astype(np.int8)
    y_va = va[label_col].to_numpy().astype(np.int8)
    ft = va["fraud_type"] if "fraud_type" in va.columns else None

    print()
    print(f"  train  {len(tr):>8,} rows  {int(y_tr.sum()):>5,} fraud")
    print(f"  val    {len(va):>8,} rows  {int(y_va.sum()):>5,} fraud")
    print()
    print(f"  baseline to beat (49 features, Task 14.4): {BASELINE_PR_AUC:.4f}")

    tuning_file = REPORTS_DIR / "task14_tuning.json"
    best = json.loads(tuning_file.read_text(encoding="utf-8"))["best_params"] \
        if tuning_file.exists() else {}
    params = final_params(best, n_jobs=n_jobs)

    results = []
    trained = {}

    for name, cols in (("base_49", base_cols), ("base_plus_graph", all_cols)):
        print()
        print(LINE)
        print(f"  {name}  ({len(cols)} features)")
        print(LINE)

        X_tr = tr[cols].astype("float32")
        X_va = va[cols].astype("float32")

        clf = lgb.LGBMClassifier(**params)
        clf.fit(X_tr, y_tr,
                eval_set=[(X_va, y_va)], eval_names=["val"],
                callbacks=[lgb.early_stopping(100, verbose=False)])

        scores = np.asarray(clf.booster_.predict(X_va), dtype=float)
        train_ap = float(average_precision_score(
            y_tr, np.asarray(clf.booster_.predict(X_tr), dtype=float)))

        r = evaluate(name, "val", y_va, scores, ft, VAL_DAYS, alerts_per_day,
                     binary_pred=(scores >= 0.5).astype(int))
        print()
        print(format_result(r))
        print()
        print(f"  trees {clf.best_iteration_}   train PR-AUC {train_ap:.4f}   "
              f"gap {train_ap - r.pr_auc:.4f}")

        results.append(r)
        trained[name] = (clf, cols, r, train_ap)

    # ---- verdict --------------------------------------------------------
    print()
    print(LINE)
    print("DID GRAPH FEATURES HELP?")
    print(LINE)
    print()
    print(comparison_table(results))

    base_ap = results[0].pr_auc
    graph_ap = results[1].pr_auc
    delta = graph_ap - base_ap

    print()
    print(f"  difference: {delta:+.4f}")
    print()
    if delta > 0.005:
        print("  YES. Graph features add signal the per-transaction")
        print("  features could not see.")
    elif delta < -0.005:
        print("  NO - the model got WORSE. More features is not better:")
        print("  weak columns add noise the trees can overfit to.")
    else:
        print("  NO MEANINGFUL CHANGE. The graph features are either")
        print("  redundant with existing ones or carry little signal in")
        print("  this generator. That is a legitimate result to report.")

    # ---- which graph features did the model actually use? ---------------
    clf, cols, r, _ = trained["base_plus_graph"]
    imp = pd.DataFrame({
        "feature": cols,
        "gain": clf.booster_.feature_importance("gain"),
    })
    imp["pct"] = 100 * imp["gain"] / imp["gain"].sum()
    imp = imp.sort_values("gain", ascending=False).reset_index(drop=True)
    imp["rank"] = imp.index + 1

    print()
    print(LINE)
    print("GRAPH FEATURES IN THE COMBINED MODEL")
    print(LINE)
    print()
    g = imp[imp["feature"].isin(graph_cols)]
    print(g[["rank", "feature", "gain", "pct"]].to_string(
        index=False, formatters={"gain": "{:,.0f}".format,
                                 "pct": "{:.2f}".format}))
    print()
    print(f"  graph features hold {g['pct'].sum():.2f}% of total gain")
    print()
    print("  top 10 overall:")
    print(imp[["rank", "feature", "pct"]].head(10).to_string(
        index=False, formatters={"pct": "{:.2f}".format}))

    # ---- save the better model ------------------------------------------
    keep = "base_plus_graph" if delta > 0.005 else "base_49"
    clf_keep, cols_keep, r_keep, _ = trained[keep]
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    model_path = MODELS_DIR / f"lgbm_{tag}.txt"
    clf_keep.booster_.save_model(str(model_path),
                                 num_iteration=clf_keep.best_iteration_)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / f"task18_graph_{tag}.json"
    out.write_text(json.dumps({
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "tag": tag,
        "kept": keep,
        "n_base": len(base_cols),
        "n_graph": len(graph_cols),
        "dropped_graph": DEAD,
        "dropped_base": DEAD_BASE,
        "base_pr_auc": base_ap,
        "graph_pr_auc": graph_ap,
        "delta": delta,
        "graph_gain_pct": float(g["pct"].sum()),
        "importance": imp.to_dict(orient="records"),
        "results": [x.to_dict() for x in results],
    }, indent=2), encoding="utf-8")

    print()
    print(LINE)
    print(f"  kept: {keep}")
    print(f"  model: {model_path}")
    print(f"  saved: {out}")
    print(LINE)


if __name__ == "__main__":
    app()