"""
scripts/inspect_model.py

Task 13.4 - what did the model actually use?

Two questions from the project record:
  1. Did it split on implied_speed_kmh? (the geo_impossible mechanism)
  2. Does merchant_txn_count dominate? (the Task 10 collusion shortcut)

    python scripts/inspect_model.py
    python scripts/inspect_model.py --tag v2
"""

from __future__ import annotations

import json

import typer

from streamguard.ml.splitter import split, PROJECT_ROOT
from streamguard.ml.lgbm import LGBMModel
from streamguard.utils.logging_config import get_logger, setup_logging

app = typer.Typer(add_completion=False)
log = get_logger(__name__)

MODELS_DIR = PROJECT_ROOT / "models"
REPORTS_DIR = PROJECT_ROOT / "reports"
LINE = "=" * 72

# Features named in the project record as worth watching.
WATCH = {
    "implied_speed_kmh": "geo_impossible mechanism - should rank high if "
                         "the Task 13 prediction held",
    "merchant_txn_count": "Task 10 COLLUSION SHORTCUT RISK - 82 for "
                          "colluding merchants vs 1,340 normal",
    "txn_count_5m": "card_testing signal (203x separation)",
    "is_manual_entry": "card_not_present signal",
    "is_new_device": "account_takeover - was the weakest at 1.95x",
}


@app.command()
def main(
    tag: str = typer.Option("v1"),
    top: int = typer.Option(20, help="How many features to list"),
) -> None:
    setup_logging()
    model_path = MODELS_DIR / f"lgbm_{tag}.txt"
    if not model_path.exists():
        print(f"ERROR: {model_path} not found. Run scripts/train_lgbm.py first.")
        raise typer.Exit(1)

    print(LINE)
    print(f"TASK 13.4 - MODEL INSPECTION  ({model_path.name})")
    print(LINE)

    model = LGBMModel.load(model_path)
    gain = model.importance("gain")
    splits = model.importance("split")

    print()
    print(f"  top {top} features by GAIN (total objective improvement):")
    print()
    print(gain.head(top).to_string(index=False,
                                   formatters={"gain": "{:,.0f}".format,
                                               "pct": "{:.2f}".format}))

    # Concentration: is the model riding a few features?
    top5 = gain.head(5)["pct"].sum()
    top10 = gain.head(10)["pct"].sum()
    unused = int((gain["gain"] == 0).sum())

    print()
    print(LINE)
    print("CONCENTRATION")
    print(LINE)
    print(f"  top 5 features   : {top5:.1f}% of total gain")
    print(f"  top 10 features  : {top10:.1f}% of total gain")
    print(f"  never split on   : {unused} of {len(gain)} features")
    print()
    if top5 > 80:
        print("  Highly concentrated. Most features contribute little.")
        print("  Not wrong, but worth noting in the report.")
    else:
        print("  Gain is spread across many features, consistent with the")
        print("  Task 12.5b finding that signal is distributed.")

    # Watched features
    print()
    print(LINE)
    print("WATCHED FEATURES  (named in the project record)")
    print(LINE)
    rank = {f: i + 1 for i, f in enumerate(gain["feature"])}
    for feat, why in WATCH.items():
        if feat in rank:
            row = gain[gain["feature"] == feat].iloc[0]
            n_split = int(splits[splits["feature"] == feat].iloc[0]["split"])
            print(f"  {feat}")
            print(f"      rank {rank[feat]} of {len(gain)}   "
                  f"gain {row['pct']:.2f}%   splits {n_split:,}")
            print(f"      {why}")
        else:
            print(f"  {feat}: NOT IN THE MODEL'S FEATURE LIST")
        print()

    # The collusion verdict
    print(LINE)
    print("COLLUSION SHORTCUT CHECK  (open item from Task 10)")
    print(LINE)
    if "merchant_txn_count" in rank:
        r = rank["merchant_txn_count"]
        pct = gain[gain["feature"] == "merchant_txn_count"].iloc[0]["pct"]
        print(f"  merchant_txn_count ranks {r} of {len(gain)}, {pct:.2f}% of gain.")
        print()
        if r <= 5:
            print("  HIGH. The model leans on merchant VOLUME. This is the")
            print("  shortcut the record warned about: real colluding")
            print("  merchants are not necessarily low-volume, so this may")
            print("  not generalise. Confirm with SHAP at Task 18 and state")
            print("  it in the report as a synthetic-data limitation.")
        elif r <= 15:
            print("  MODERATE. Used, but not dominant. Keep watching;")
            print("  confirm with SHAP at Task 18.")
        else:
            print("  LOW. The model is not leaning on merchant volume.")
            print("  The shortcut risk looks smaller than feared - but")
            print("  gain importance splits credit between correlated")
            print("  features, so SHAP at Task 18 is still the real check.")
    else:
        print("  merchant_txn_count is not a feature in this model.")

    print()
    print(LINE)
    print("  Gain importance is NOT causal and NOT the same as SHAP.")
    print("  Correlated features split credit between them arbitrarily.")
    print("  It says what the model used, not what matters in the world.")
    print(LINE)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / f"task13_importance_{tag}.json"
    out.write_text(json.dumps({
        "tag": tag,
        "top_5_pct": float(top5),
        "top_10_pct": float(top10),
        "n_unused": unused,
        "gain": gain.to_dict(orient="records"),
    }, indent=2), encoding="utf-8")
    print(f"  saved: {out}")


if __name__ == "__main__":
    app()