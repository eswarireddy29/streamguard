"""
scripts/retrain_from_labels.py

Task 30 - the closed loop: analyst verdicts become training labels.

THE ARCHITECTURE PROMISE FROM TASK 1. The record says "a closed loop:
analyst labels flow back into retraining". This is that loop, and it
is the only source of truth a deployed fraud model ever gets - nobody
hands you labelled data after go-live.

THREE THINGS THAT MAKE THIS HONEST:

  1. Only confirmed_fraud and legitimate are used. "inconclusive" is
     recorded but never trained on - an analyst who could not decide
     has not said the transaction was legitimate, and training on it
     as a negative teaches the model that genuine fraud is normal.

  2. A retrained model must BEAT the current one on the same
     validation block before it replaces anything. "Newer" is not
     "better", and a retraining loop that ships every run will
     eventually ship a worse model.

  3. Nothing is deployed automatically. The script reports and stops.
     Promotion is a human decision.

    python scripts/retrain_from_labels.py
    python scripts/retrain_from_labels.py --min-labels 50
"""

from __future__ import annotations

import json
from datetime import datetime

import lightgbm as lgb
import numpy as np
import pandas as pd
import typer
from sqlalchemy import text

from streamguard.db.session import get_session
from streamguard.ml.splitter import split, PROJECT_ROOT
from streamguard.ml.tuning import final_params
from streamguard.ml.metrics import evaluate, format_result, comparison_table
from streamguard.ml.lgbm import LGBMModel
from streamguard.utils.logging_config import get_logger, setup_logging

app = typer.Typer(add_completion=False)
log = get_logger(__name__)

REPORTS_DIR = PROJECT_ROOT / "reports"
MODELS_DIR = PROJECT_ROOT / "models"
LINE = "=" * 72

# Below this, retraining is noise. A handful of labels cannot shift a
# model trained on two thousand frauds, and pretending otherwise
# produces a confident model built on a rounding error.
MIN_LABELS = 20


def fetch_labels() -> pd.DataFrame:
    """Analyst verdicts, joined to the features that were scored.

    The features come from decisions.features (JSONB) - the EXACT
    vector the model saw at decision time, stored at Task 22. That
    matters: recomputing them now would use today's state, not the
    state as it stood, and the label would be attached to the wrong
    inputs. Task 4B called this out as how training/serving skew is
    DETECTED; here it is what makes retraining correct.
    """
    with get_session() as s:
        rows = s.execute(text("""
            SELECT c.case_ref, c.verdict, c.verdict_at, c.assigned_to,
                   d.score, d.model_version, d.features,
                   t.transaction_ref, t.is_fraud AS generator_truth
            FROM cases c
            JOIN decisions d ON d.id = c.decision_id
            JOIN transactions t ON t.id = c.transaction_id
            WHERE c.verdict IN ('confirmed_fraud', 'legitimate')
            ORDER BY c.verdict_at
        """)).fetchall()

    if not rows:
        return pd.DataFrame()

    records = []
    for r in rows:
        features = r[6] or {}
        records.append({
            "case_ref": r[0],
            "verdict": r[1],
            "label": 1 if r[1] == "confirmed_fraud" else 0,
            "verdict_at": r[2],
            "analyst": r[3],
            "score": float(r[4]),
            "model_version": r[5],
            "transaction_ref": r[7],
            "generator_truth": bool(r[8]),
            **{k: float(v) for k, v in features.items()
               if isinstance(v, (int, float))},
        })
    return pd.DataFrame(records)


@app.command()
def main(
    min_labels: int = typer.Option(MIN_LABELS),
    current_tag: str = typer.Option("lgbm_v6"),
    new_tag: str = typer.Option("lgbm_retrained"),
    n_jobs: int = typer.Option(6),
    alerts_per_day: int = typer.Option(100),
) -> None:
    setup_logging()
    print(LINE)
    print("TASK 30 - RETRAINING FROM ANALYST LABELS")
    print(LINE)

    labels = fetch_labels()

    print()
    print(LINE)
    print("1. LABEL SUPPLY")
    print(LINE)
    print()
    if len(labels) == 0:
        print("  No usable verdicts yet.")
        print()
        print("  Work some cases in the console first - or run:")
        print("      python scripts/test_cases.py")
        raise typer.Exit(0)

    counts = labels["verdict"].value_counts().to_dict()
    print(f"  usable labels     {len(labels)}")
    for v, n in counts.items():
        print(f"    {v:<20} {n}")
    print(f"  analysts          "
          f"{', '.join(sorted(labels['analyst'].dropna().unique()))}")
    print(f"  model versions    "
          f"{', '.join(sorted(labels['model_version'].dropna().unique()))}")

    # ---- how good are the analysts? ---------------------------------------
    # This project has generator ground truth, which a real deployment
    # does not. Comparing the verdict against it measures the LABEL
    # QUALITY the loop depends on - and it is the honest way to say
    # how much a retrained model can be trusted.
    agree = int((labels["label"] == labels["generator_truth"].astype(int)).sum())
    print()
    print(f"  analyst agreement with generator truth: "
          f"{agree}/{len(labels)} ({100 * agree / len(labels):.0f}%)")
    print()
    print("  A real deployment has no ground truth to compare against -")
    print("  this check exists only because the data is synthetic. It")
    print("  measures the LABEL QUALITY the whole loop depends on.")

    if len(labels) < min_labels:
        print()
        print(LINE)
        print("NOT ENOUGH LABELS")
        print(LINE)
        print()
        print(f"  {len(labels)} labels, {min_labels} needed.")
        print()
        print("  Retraining on a handful of labels is noise dressed as")
        print("  learning: they cannot shift a model trained on 2,034")
        print("  frauds, and the result would be a confident model built")
        print("  on a rounding error.")
        raise typer.Exit(0)

    if labels["label"].nunique() < 2:
        print()
        print("  All labels are the same class. A model needs both.")
        raise typer.Exit(0)

    # ---- retrain -----------------------------------------------------------
    # Load whichever feature file matches the incumbent. Task 18A
    # wrote features_graph.parquet (58 features) separately from
    # features.parquet (49) so earlier results stayed reproducible.
    # Comparing a 58-feature model scored on 49 features - with the
    # rest zero-filled - is not a comparison, it is a handicap match.
    graph_path = PROJECT_ROOT / "data" / "processed" / "features_graph.parquet"
    source = graph_path if graph_path.exists() else None
    blocks = split(path=source, save_manifest=False) if source \
        else split(save_manifest=False)
    train, val = blocks["train"], blocks["val"]
    val_days = val.day_range[1] - val.day_range[0] + 1
    ft = val.meta["fraud_type"] if "fraud_type" in val.meta.columns else None

    feature_cols = [c for c in train.X.columns if c in labels.columns]
    missing = [c for c in train.X.columns if c not in labels.columns]

    print()
    print(LINE)
    print("2. RETRAINING")
    print(LINE)
    print()
    print(f"  base training rows   {len(train.X):,} "
          f"({int(train.y.sum()):,} fraud)")
    print(f"  analyst labels       {len(labels)}")
    print(f"  features matched     {len(feature_cols)} of {len(train.X.columns)}")
    if missing:
        print(f"  not in stored JSONB  {len(missing)}: {missing[:4]}...")

    # The analyst-labelled rows are APPENDED to the training set, not
    # used alone. A few dozen labels cannot train a model; they can
    # correct one. Weighting them higher is a deliberate choice: they
    # are the only labels that came from a human looking at the case.
    extra_X = labels[feature_cols].astype("float32")
    extra_y = labels["label"].to_numpy().astype(np.int8)

    X_combined = pd.concat([train.X[feature_cols], extra_X],
                           ignore_index=True)
    y_combined = np.concatenate([train.y, extra_y])

    LABEL_WEIGHT = 10.0
    weights = np.concatenate([
        np.ones(len(train.y)),
        np.full(len(extra_y), LABEL_WEIGHT),
    ])
    print(f"  combined rows        {len(X_combined):,}")
    print(f"  analyst label weight {LABEL_WEIGHT}x "
          "(a human looked at these)")

    tuning_file = REPORTS_DIR / "task14_tuning.json"
    best = json.loads(tuning_file.read_text(encoding="utf-8"))["best_params"] \
        if tuning_file.exists() else {}
    params = final_params(best, n_jobs=n_jobs)

    clf = lgb.LGBMClassifier(**params)
    clf.fit(X_combined, y_combined, sample_weight=weights,
            eval_set=[(val.X[feature_cols], val.y)], eval_names=["val"],
            callbacks=[lgb.early_stopping(100, verbose=False)])

    new_scores = np.asarray(
        clf.booster_.predict(val.X[feature_cols]), dtype=float)
    r_new = evaluate("retrained", "val", val.y, new_scores, ft,
                     val_days, alerts_per_day)

    # ---- compare against the incumbent --------------------------------------
    print()
    print(LINE)
    print("3. IS IT BETTER?")
    print(LINE)

    current_path = MODELS_DIR / f"{current_tag}.txt"
    r_old = None
    if current_path.exists():
        old = LGBMModel.load(current_path)
        old_cols = old.feature_names

        def frame_for(block):
            parts = {}
            for c in old_cols:
                if c in block.X.columns:
                    parts[c] = block.X[c].to_numpy()
                elif c in block.meta.columns:
                    parts[c] = block.meta[c].to_numpy()
                else:
                    # Never silently zero-fill a model's input. A
                    # missing feature means the wrong file is loaded,
                    # and the comparison that follows would be a lie.
                    raise KeyError(
                        f"{c} is in neither X nor meta - the loaded "
                        "feature file does not match this model")
            return pd.DataFrame(parts, columns=old_cols).astype("float32")

        old_scores = old.score_samples(frame_for(val))
        r_old = evaluate(current_tag, "val", val.y, old_scores, ft,
                         val_days, alerts_per_day)

    print()
    print(comparison_table([x for x in (r_old, r_new) if x]))

    promote = False
    if r_old:
        delta = r_new.pr_auc - r_old.pr_auc
        print()
        print(f"  difference: {delta:+.4f}")
        print()
        if delta > 0.002:
            promote = True
            print("  BETTER. The retrained model beats the incumbent on the")
            print("  same validation block.")
        elif delta < -0.002:
            print("  WORSE. Do NOT promote. 'Newer' is not 'better', and a")
            print("  loop that ships every run eventually ships a bad model.")
        else:
            print("  NO MEANINGFUL CHANGE. Too few labels to move the model.")
            print("  That is the expected result at this label count, and")
            print("  it is worth reporting rather than hiding.")

    model_path = MODELS_DIR / f"{new_tag}.txt"
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    clf.booster_.save_model(str(model_path),
                            num_iteration=clf.best_iteration_)

    print()
    print(LINE)
    print("4. WHAT HAPPENS NEXT")
    print(LINE)
    print()
    print(f"  saved: {model_path}")
    print()
    print("  NOTHING IS DEPLOYED AUTOMATICALLY. The model is written to")
    print("  disk and the comparison is reported. Promotion is a human")
    print("  decision, because a retraining loop that promotes itself")
    print("  has no way to refuse a bad model.")
    if promote:
        print()
        print(f"  To promote:  copy {new_tag}.txt over {current_tag}.txt")
        print("  and restart the scoring service.")

    out = REPORTS_DIR / "task30_retrain.json"
    out.write_text(json.dumps({
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "n_labels": len(labels),
        "label_counts": counts,
        "analyst_agreement": agree / len(labels),
        "features_matched": len(feature_cols),
        "label_weight": LABEL_WEIGHT,
        "current": r_old.to_dict() if r_old else None,
        "retrained": r_new.to_dict(),
        "delta": (r_new.pr_auc - r_old.pr_auc) if r_old else None,
        "recommend_promote": promote,
    }, indent=2, default=float), encoding="utf-8")

    print()
    print(f"  saved: {out}")
    print(LINE)


if __name__ == "__main__":
    app()