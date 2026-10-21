"""
scripts/check_drift.py

Task 30 - has the input distribution moved since training?

Compares the TRAINING block against the TEST block. In production the
comparison would be training-vs-last-7-days; here the test block is
the newest data the model has not learned from, which is the same
question.

Runs my own PSI/KS first, then Evidently over the same data as a
cross-check. If the two disagree, one of them has a bug - and that is
worth knowing.

    python scripts/check_drift.py
    python scripts/check_drift.py --no-evidently
"""

from __future__ import annotations

import json
from datetime import datetime

import numpy as np
import pandas as pd
import typer

from streamguard.ml.drift import (
    feature_drift, prediction_drift, summarise,
    PSI_NO_CHANGE, PSI_MODERATE,
)
from streamguard.ml.splitter import split, load_test, PROJECT_ROOT
from streamguard.ml.lgbm import LGBMModel
from streamguard.utils.logging_config import get_logger, setup_logging

app = typer.Typer(add_completion=False)
log = get_logger(__name__)

REPORTS_DIR = PROJECT_ROOT / "reports"
MODELS_DIR = PROJECT_ROOT / "models"
LINE = "=" * 72


@app.command()
def main(
    tag: str = typer.Option("lgbm_v6"),
    top: int = typer.Option(15),
    evidently: bool = typer.Option(False, help="Also run Evidently"),
) -> None:
    setup_logging()
    print(LINE)
    print("TASK 30 - DRIFT DETECTION")
    print(LINE)

    # The graph model needs features_graph.parquet (58 features), not
    # features.parquet (49). Task 18A wrote a separate file so the
    # Task 12-17 results stayed reproducible; the drift check has to
    # read whichever one matches the model being monitored.
    graph_path = PROJECT_ROOT / "data" / "processed" / "features_graph.parquet"
    source = graph_path if graph_path.exists() else None

    blocks = split(path=source, save_manifest=False) if source \
        else split(save_manifest=False)
    train = blocks["train"]
    current = load_test(
        path=source,
        reason="Task 30 drift baseline: comparing training against the "
               "newest data the model has not learned from",
    ) if source else load_test(
        reason="Task 30 drift baseline: comparing training against the "
               "newest data the model has not learned from")

    features = list(train.X.columns)
    print(f"  source     {source.name if source else 'features.parquet'}")

    print()
    print(f"  reference  {len(train.X):,} rows (training, days "
          f"{train.day_range[0]}-{train.day_range[1]})")
    print(f"  current    {len(current.X):,} rows (test, days "
          f"{current.day_range[0]}-{current.day_range[1]})")
    print(f"  features   {len(features)}")
    print()
    print(f"  PSI thresholds: < {PSI_NO_CHANGE} stable, "
          f"< {PSI_MODERATE} moderate, above that significant")
    print("  (conventional banking rules of thumb, not laws)")

    # ---- feature drift --------------------------------------------------
    drift = feature_drift(train.X, current.X, features)
    summary = summarise(drift)

    print()
    print(LINE)
    print("1. FEATURE DRIFT (my PSI / KS)")
    print(LINE)
    print()
    print(f"  {'feature':<28}{'PSI':>8}{'KS':>8}{'ref mean':>12}"
          f"{'cur mean':>12}{'verdict':>13}")
    print("  " + "-" * 81)
    for _, r in drift.head(top).iterrows():
        print(f"  {r['feature']:<28}{r['psi']:>8.4f}{r['ks_statistic']:>8.4f}"
              f"{r['reference_mean']:>12,.3f}{r['current_mean']:>12,.3f}"
              f"{r['verdict']:>13}")

    print()
    print(f"  {summary['stable']} stable, {summary['moderate']} moderate, "
          f"{summary['significant']} significant")
    print(f"  worst: {summary['worst_feature']} "
          f"(PSI {summary['worst_psi']:.4f})")

    # ---- prediction drift ------------------------------------------------
    model_path = MODELS_DIR / f"{tag}.txt"
    pred = None
    if model_path.exists():
        model = LGBMModel.load(model_path)
        cols = model.feature_names

        def frame_for(block):
            """Rebuild the model's 58 columns.

            split() builds X from FEATURE_NAMES, which is the 49 base
            features - the 10 graph columns are in the file but land
            in meta. The model needs both, in its own order.
            """
            parts = {}
            for c in cols:
                if c in block.X.columns:
                    parts[c] = block.X[c].to_numpy()
                elif c in block.meta.columns:
                    parts[c] = block.meta[c].to_numpy()
                else:
                    raise KeyError(f"{c} is in neither X nor meta")
            return pd.DataFrame(parts, columns=cols).astype("float32")

        ref_scores = model.score_samples(frame_for(train))
        cur_scores = model.score_samples(frame_for(current))
        pred = prediction_drift(ref_scores, cur_scores)

        print()
        print(LINE)
        print("2. PREDICTION DRIFT (the output, not the inputs)")
        print(LINE)
        print()
        print(f"  PSI               {pred['psi']:.4f}  ({pred['verdict']})")
        print(f"  KS statistic      {pred['ks_statistic']:.4f}")
        print(f"  mean score        {pred['reference_mean']:.5f} -> "
              f"{pred['current_mean']:.5f}")
        print(f"  flagged at 0.0306 {pred['reference_flagged_pct']:.3f}% -> "
              f"{pred['current_flagged_pct']:.3f}%")
        print()
        print("  This is the signal that matters most. An input can move")
        print("  without changing what the model concludes; output drift")
        print("  means its behaviour changed, and that reaches a customer.")

    # ---- Evidently cross-check --------------------------------------------
    evidently_result = None
    if evidently:
        print()
        print(LINE)
        print("3. EVIDENTLY CROSS-CHECK")
        print(LINE)
        try:
            from evidently.report import Report
            from evidently.metric_preset import DataDriftPreset

            # A sample: Evidently over 550k x 58 is slow and heavy on
            # 8 GB, and drift detection does not need every row.
            n = min(20_000, len(train.X), len(current.X))
            ref_s = train.X.sample(n, random_state=42)
            cur_s = current.X.sample(n, random_state=42)

            report = Report(metrics=[DataDriftPreset()])
            report.run(reference_data=ref_s, current_data=cur_s)

            out_html = REPORTS_DIR / "task30_drift.html"
            REPORTS_DIR.mkdir(parents=True, exist_ok=True)
            report.save_html(str(out_html))

            d = report.as_dict()
            res = d["metrics"][0]["result"]
            evidently_result = {
                "n_features": res.get("number_of_columns"),
                "n_drifted": res.get("number_of_drifted_columns"),
                "share_drifted": res.get("share_of_drifted_columns"),
                "dataset_drift": res.get("dataset_drift"),
                "sample_size": n,
            }
            print()
            print(f"  features compared  {evidently_result['n_features']}")
            print(f"  drifted            {evidently_result['n_drifted']}")
            print(f"  share drifted      "
                  f"{evidently_result['share_drifted']:.3f}")
            print(f"  dataset drift      {evidently_result['dataset_drift']}")
            print(f"  (sampled {n:,} rows per side)")
            print()
            print(f"  report: {out_html}")

            mine = summary["significant"] + summary["moderate"]
            theirs = evidently_result["n_drifted"] or 0
            print()
            print(f"  my count (moderate+significant): {mine}")
            print(f"  Evidently's drifted count      : {theirs}")
            if abs(mine - theirs) <= max(3, 0.2 * len(features)):
                print("  The two broadly agree.")
            else:
                print("  THEY DISAGREE. Worth understanding before trusting")
                print("  either - they use different tests and thresholds,")
                print("  but a large gap means one of them is wrong.")

        except Exception as exc:
            print()
            print(f"  Evidently failed: {exc}")
            print("  The PSI/KS results above stand on their own.")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / "task30_drift.json"
    out.write_text(json.dumps({
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "reference": {"rows": len(train.X), "days": list(train.day_range)},
        "current": {"rows": len(current.X), "days": list(current.day_range)},
        "summary": summary,
        "features": drift.to_dict(orient="records"),
        "prediction_drift": pred,
        "evidently": evidently_result,
    }, indent=2, default=float), encoding="utf-8")

    print()
    print(LINE)
    print(f"  saved: {out}")
    print(LINE)


if __name__ == "__main__":
    app()