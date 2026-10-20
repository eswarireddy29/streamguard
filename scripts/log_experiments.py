"""
scripts/log_experiments.py

Task 18C - backfill every model version from Tasks 12-18 into MLflow.

Reads the report JSON files already written by earlier tasks, so the
history is reconstructed from measurements rather than retyped.

    python scripts/log_experiments.py
    mlflow ui --backend-store-uri mlruns
"""

from __future__ import annotations

import typer

from streamguard.ml.tracking import configure, log_run, load_report, MLRUNS
from streamguard.ml.splitter import PROJECT_ROOT
from streamguard.utils.logging_config import get_logger, setup_logging

app = typer.Typer(add_completion=False)
log = get_logger(__name__)

REPORTS = PROJECT_ROOT / "reports"
MODELS = PROJECT_ROOT / "models"
LINE = "=" * 72


@app.command()
def main() -> None:
    setup_logging()
    print(LINE)
    print("TASK 18C - MLFLOW BACKFILL")
    print(LINE)

    uri = configure()
    print()
    print(f"  tracking uri: {uri}")

    logged = []

    # ---- Task 12 baselines --------------------------------------------
    base = load_report(REPORTS / "task12_baselines.json")
    for r in base.get("results", []):
        rec = log_run(
            name=f"task12_{r['model']}",
            params={"task": 12, "model_type": r["model"],
                    "n_features": 49, "block": "validation"},
            metrics={"pr_auc": r["pr_auc"], "roc_auc": r["roc_auc"],
                     "precision_at_k": r["precision_at_k"],
                     "recall_at_k": r["recall_at_k"],
                     "lift_over_random": r["lift_over_random"],
                     "per_pattern": r.get("per_pattern_recall_at_k", {})},
            tags={"phase": "D", "task": "12", "kind": "baseline"},
        )
        logged.append(rec)

    # ---- Task 14 imbalance comparison ----------------------------------
    imb = load_report(REPORTS / "task14_imbalance.json")
    for r in imb.get("results", []):
        rec = log_run(
            name=f"task14_imbalance_{r['strategy']}",
            params={"task": 14, "model_type": "lightgbm",
                    "imbalance_strategy": r["strategy"], "n_features": 49},
            metrics={"pr_auc": r["pr_auc"], "train_pr_auc": r["train_pr_auc"],
                     "overfit_gap": r["gap"],
                     "precision_at_k": r["precision_at_k"],
                     "trees": r["trees"]},
            tags={"phase": "D", "task": "14", "kind": "imbalance"},
        )
        logged.append(rec)

    # ---- Task 14 tuned model -------------------------------------------
    fin = load_report(REPORTS / "task14_final_v4.json")
    if fin:
        r = fin["result"]
        rec = log_run(
            name="task14_tuned_v4",
            params={"task": 14, "model_type": "lightgbm", "n_features": 49,
                    "imbalance_strategy": "none",
                    **{k: v for k, v in fin.get("params", {}).items()
                       if k in ("num_leaves", "max_depth", "min_child_samples",
                                "subsample", "colsample_bytree", "reg_lambda",
                                "learning_rate")}},
            metrics={"pr_auc": r["pr_auc"], "train_pr_auc": fin["train_pr_auc"],
                     "overfit_gap": fin["gap"],
                     "precision_at_k": r["precision_at_k"],
                     "recall_at_k": r["recall_at_k"],
                     "trees": fin["best_iteration"],
                     "per_pattern": r.get("per_pattern_recall_at_k", {})},
            artifacts=[MODELS / "lgbm_v4.txt"],
            tags={"phase": "D", "task": "14", "kind": "tuned"},
        )
        logged.append(rec)

    # ---- Task 15 test evaluation ----------------------------------------
    test = load_report(REPORTS / "task15_test_v4.json")
    if test:
        r = test["result"]
        cal = test.get("calibration", {})
        rec = log_run(
            name="task15_TEST_v4",
            params={"task": 15, "model_type": "lightgbm", "n_features": 49,
                    "block": "TEST"},
            metrics={"pr_auc": r["pr_auc"], "roc_auc": r["roc_auc"],
                     "precision_at_k": r["precision_at_k"],
                     "recall_at_k": r["recall_at_k"],
                     "validation_pr_auc": test["validation_pr_auc"],
                     "val_minus_test": test["val_minus_test"],
                     "ece": cal.get("ece", float("nan")),
                     "brier": cal.get("brier", float("nan")),
                     "per_pattern": r.get("per_pattern_recall_at_k", {})},
            tags={"phase": "D", "task": "15", "kind": "HELD_OUT_TEST"},
        )
        logged.append(rec)

    # ---- Task 16 threshold -----------------------------------------------
    thr = load_report(REPORTS / "task16_threshold_v4.json")
    if thr:
        o = thr["optimum"]
        t = thr.get("test", {}).get("at_chosen_threshold", {})
        rec = log_run(
            name="task16_cost_threshold",
            params={"task": 16, "model_type": "lightgbm",
                    "fn_cost": thr["costs"]["false_negative"],
                    "fp_cost": thr["costs"]["false_positive"],
                    "cost_ratio": thr["costs"]["ratio"]},
            metrics={"threshold": o["threshold"],
                     "theoretical_threshold": thr["theoretical_threshold"],
                     "val_cost": o["total_cost"],
                     "val_precision": o["precision"],
                     "val_recall": o["recall"],
                     "test_cost": t.get("total_cost", float("nan")),
                     "test_recall": t.get("recall", float("nan")),
                     "test_saving": thr.get("test", {}).get("saving", float("nan"))},
            tags={"phase": "D", "task": "16", "kind": "threshold"},
        )
        logged.append(rec)

    # ---- Task 17 anomaly --------------------------------------------------
    ano = load_report(REPORTS / "task17_anomaly.json")
    for r in ano.get("results", []):
        rec = log_run(
            name=f"task17_{r['model']}",
            params={"task": 17, "model_type": r["model"],
                    "supervised": r["model"] == "lightgbm"},
            metrics={"pr_auc": r["pr_auc"], "roc_auc": r["roc_auc"],
                     "precision_at_k": r["precision_at_k"],
                     "recall_at_k": r["recall_at_k"],
                     "per_pattern": r.get("per_pattern_recall_at_k", {})},
            tags={"phase": "D", "task": "17", "kind": "anomaly"},
        )
        logged.append(rec)

    # ---- Task 17 novel-fraud holdout ---------------------------------------
    nov = load_report(REPORTS / "task17_novel_fraud.json")
    for r in nov.get("results", []):
        rec = log_run(
            name=f"task17_holdout_{r['pattern']}",
            params={"task": 17, "held_out_pattern": r["pattern"],
                    "n_removed": r["n_train_removed"]},
            metrics={"supervised_recall": r["supervised_recall"],
                     "isolation_recall": r["isolation_recall"],
                     "mahalanobis_recall": r["mahalanobis_recall"],
                     "supervised_pr_auc": r["supervised_pr_auc"],
                     "n_val": r["n_val"]},
            tags={"phase": "D", "task": "17", "kind": "holdout"},
        )
        logged.append(rec)

    # ---- Task 18 graph ------------------------------------------------------
    for tag in ("v5", "v6"):
        gr = load_report(REPORTS / f"task18_graph_{tag}.json")
        if not gr:
            continue
        for res in gr.get("results", []):
            rec = log_run(
                name=f"task18_{tag}_{res['model']}",
                params={"task": 18, "model_type": "lightgbm",
                        "n_features": (gr["n_base"] + gr["n_graph"]
                                       if res["model"] == "base_plus_graph"
                                       else gr["n_base"]),
                        "graph_features": res["model"] == "base_plus_graph",
                        "dropped": ",".join(gr.get("dropped_base", [])
                                            + gr.get("dropped_graph",
                                                     gr.get("dropped", [])))},
                metrics={"pr_auc": res["pr_auc"], "roc_auc": res["roc_auc"],
                         "precision_at_k": res["precision_at_k"],
                         "recall_at_k": res["recall_at_k"],
                         "graph_gain_pct": gr.get("graph_gain_pct", 0.0),
                         "per_pattern": res.get("per_pattern_recall_at_k", {})},
                artifacts=[MODELS / f"lgbm_{tag}.txt"],
                tags={"phase": "D", "task": "18", "kind": "graph"},
            )
            logged.append(rec)

    # ---- summary -------------------------------------------------------------
    print()
    print(LINE)
    print(f"LOGGED {len(logged)} RUNS")
    print(LINE)
    print()
    print(f"  {'run':<38}{'pr_auc':>9}{'prec@k':>9}")
    print("  " + "-" * 56)
    for r in logged:
        pr = r.metrics.get("pr_auc", r.metrics.get("supervised_pr_auc"))
        pk = r.metrics.get("precision_at_k")
        print(f"  {r.name:<38}"
              f"{pr if pr is not None else float('nan'):>9.4f}"
              f"{pk if pk is not None else float('nan'):>9.4f}")

    print()
    print(LINE)
    print("OPEN THE UI")
    print(LINE)
    print()
    print("  In a SECOND terminal, with the venv active:")
    print()
    print("      mlflow ui --backend-store-uri mlruns")
    print()
    print("  Then open http://127.0.0.1:5000 in a browser.")
    print("  Ctrl+C in that terminal stops it.")
    print()
    print(f"  runs folder: {MLRUNS}")
    print(LINE)


if __name__ == "__main__":
    app()