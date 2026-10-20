"""
scripts/optimize_threshold.py

Task 16 - find the threshold that costs the least money.

The threshold is CHOSEN ON VALIDATION and then REPORTED on test. It is
not chosen on test - that would be tuning against the held-out data.

    python scripts/optimize_threshold.py
    python scripts/optimize_threshold.py --fn-cost 8000 --fp-cost 150
"""

from __future__ import annotations

import json
from datetime import datetime

import typer

from streamguard.ml.splitter import split, load_test, PROJECT_ROOT
from streamguard.ml.lgbm import LGBMModel
from streamguard.ml.costs import (
    CostModel, optimal, cost_at, three_way, format_result,
    theoretical_threshold,
)
from streamguard.utils.logging_config import get_logger, setup_logging

app = typer.Typer(add_completion=False)
log = get_logger(__name__)

MODELS_DIR = PROJECT_ROOT / "models"
REPORTS_DIR = PROJECT_ROOT / "reports"
LINE = "=" * 72


@app.command()
def main(
    tag: str = typer.Option("v4"),
    fn_cost: float = typer.Option(5000.0, help="Cost of missing one fraud"),
    fp_cost: float = typer.Option(200.0, help="Cost of blocking one customer"),
    review_cost: float = typer.Option(50.0, help="Analyst time per review"),
    reviews_per_day: int = typer.Option(100, help="Analyst capacity"),
    on_test: bool = typer.Option(
        True, help="Also report the chosen threshold on test"),
) -> None:
    setup_logging()
    model_path = MODELS_DIR / f"lgbm_{tag}.txt"
    if not model_path.exists():
        print(f"ERROR: {model_path} not found.")
        raise typer.Exit(1)

    costs = CostModel(false_negative=fn_cost, false_positive=fp_cost,
                      review=review_cost)

    print(LINE)
    print("TASK 16 - COST-BASED THRESHOLD")
    print(LINE)
    print()
    print(f"  missing one fraud      Rs {costs.false_negative:>8,.0f}")
    print(f"  blocking one customer  Rs {costs.false_positive:>8,.0f}")
    print(f"  one analyst review     Rs {costs.review:>8,.0f}")
    print(f"  asymmetry              {costs.ratio:.1f} : 1")
    print()
    print("  ASSUMPTIONS, not measured figures. A real bank would take")
    print("  these from chargeback data and churn analysis.")

    blocks = split(save_manifest=False)
    val = blocks["val"]
    model = LGBMModel.load(model_path)
    val_scores = model.score_samples(val.X)

    # ---- the textbook answer -----------------------------------------
    theory = theoretical_threshold(costs)
    print()
    print(LINE)
    print("1. THE THEORETICAL THRESHOLD")
    print(LINE)
    print()
    print("  Block when the expected cost of approving exceeds the")
    print("  expected cost of blocking:")
    print()
    print("      p x FN  >  (1 - p) x FP")
    print("      p       >  FP / (FP + FN)")
    print()
    print(f"      p  >  {costs.false_positive:,.0f} / "
          f"({costs.false_positive:,.0f} + {costs.false_negative:,.0f})"
          f"  =  {theory:.5f}")
    print()
    print("  This holds only because Task 15 confirmed the probabilities")
    print("  are calibrated (ECE 0.00053).")

    # ---- the measured answer -----------------------------------------
    best, df = optimal(val.y, val_scores, costs)
    default = cost_at(val.y, val_scores, 0.5, costs)
    theory_r = cost_at(val.y, val_scores, theory, costs)

    print()
    print(LINE)
    print("2. ON VALIDATION - THREE THRESHOLDS COMPARED")
    print(LINE)
    print()
    print(format_result(default, costs, "default 0.5"))
    print()
    print(format_result(theory_r, costs, f"theoretical {theory:.4f}"))
    print()
    print(format_result(best, costs, "MEASURED OPTIMUM"))

    saving = default.total_cost - best.total_cost
    print()
    print(f"  optimum vs default 0.5: Rs {saving:,.0f} saved on "
          f"{len(val.y):,} transactions")
    if default.total_cost:
        print(f"  that is {100 * saving / default.total_cost:.1f}% of the "
              "cost at 0.5")

    # ---- the cost curve ------------------------------------------------
    print()
    print(LINE)
    print("3. COST CURVE (sampled)")
    print(LINE)
    print()
    print(f"  {'threshold':>11}{'caught':>9}{'missed':>8}"
          f"{'blocked':>9}{'cost Rs':>14}")
    print("  " + "-" * 51)
    show = df.iloc[::max(1, len(df) // 18)]
    for _, r in show.iterrows():
        mark = "  <-- optimum" if abs(r["threshold"] - best.threshold) < 1e-9 else ""
        print(f"  {r['threshold']:>11.5f}{int(r['tp']):>9,}{int(r['fn']):>8,}"
              f"{int(r['fp']):>9,}{r['total_cost']:>14,.0f}{mark}")

    # ---- three-way decision ---------------------------------------------
    print()
    print(LINE)
    print("4. THREE-WAY DECISION (approve / review / block)")
    print(LINE)
    print()
    print("  A binary decision throws away the model's uncertainty.")
    print("  Middle scores are exactly the cases worth analyst time.")
    print()

    val_days = val.day_range[1] - val.day_range[0] + 1
    capacity = reviews_per_day * val_days

    # Review band: everything above the optimum that an analyst can see.
    import numpy as np
    review_t = float(np.quantile(val_scores, 1 - capacity / len(val_scores)))
    review_t = min(review_t, best.threshold)

    tw = three_way(val.y, val_scores, costs,
                   block_threshold=best.threshold,
                   review_threshold=review_t)

    print(f"  block   >= {tw['block_threshold']:.5f}   "
          f"{tw['n_blocked']:>7,} rows   "
          f"{tw['fraud_blocked']:>4,} fraud, {tw['legit_blocked']:>4,} legit")
    print(f"  review  >= {tw['review_threshold']:.5f}   "
          f"{tw['n_review']:>7,} rows   "
          f"{tw['fraud_in_review']:>4,} fraud "
          f"({tw['n_review'] / val_days:.0f}/day vs {reviews_per_day} capacity)")
    print(f"  approve  < {tw['review_threshold']:.5f}   "
          f"{tw['n_approved']:>7,} rows   "
          f"{tw['fraud_missed']:>4,} fraud MISSED")
    print()
    print(f"  total cost Rs {tw['total_cost']:,.0f}   "
          f"(per 1,000: Rs {tw['cost_per_1000']:,.2f})")
    print()
    if tw["total_cost"] < best.total_cost:
        print(f"  Cheaper than the binary optimum by "
              f"Rs {best.total_cost - tw['total_cost']:,.0f}.")
    else:
        print(f"  More expensive than the binary optimum by "
              f"Rs {tw['total_cost'] - best.total_cost:,.0f}.")
        print("  The review band costs analyst time without catching")
        print("  enough extra fraud to pay for it here.")

    payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "tag": tag,
        "costs": {"false_negative": costs.false_negative,
                  "false_positive": costs.false_positive,
                  "review": costs.review, "ratio": costs.ratio},
        "theoretical_threshold": theory,
        "chosen_on": "validation",
        "optimum": best.to_dict(),
        "default_0.5": default.to_dict(),
        "theoretical": theory_r.to_dict(),
        "three_way": tw,
    }

    # ---- apply to test ---------------------------------------------------
    if on_test:
        print()
        print(LINE)
        print("5. THE CHOSEN THRESHOLD, APPLIED TO TEST")
        print(LINE)
        print()
        print("  The threshold was chosen on VALIDATION. This only reports")
        print("  what it does on test - nothing is re-optimised here.")

        test = load_test(
            reason=f"Task 16 reporting the validation-chosen threshold, {tag}"
        )
        test_scores = model.score_samples(test.X)

        t_best = cost_at(test.y, test_scores, best.threshold, costs)
        t_default = cost_at(test.y, test_scores, 0.5, costs)

        print()
        print(format_result(t_default, costs, "default 0.5"))
        print()
        print(format_result(t_best, costs, "validation-chosen threshold"))

        t_saving = t_default.total_cost - t_best.total_cost
        print()
        print(f"  saved on test: Rs {t_saving:,.0f} across "
              f"{len(test.y):,} transactions")

        payload["test"] = {
            "at_chosen_threshold": t_best.to_dict(),
            "at_default": t_default.to_dict(),
            "saving": t_saving,
        }

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / f"task16_threshold_{tag}.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    df.to_csv(REPORTS_DIR / f"task16_cost_curve_{tag}.csv", index=False)

    print()
    print(LINE)
    print(f"  saved: {out}")
    print(f"  curve: {REPORTS_DIR / f'task16_cost_curve_{tag}.csv'}")
    print(LINE)


if __name__ == "__main__":
    app()