"""
scripts/diagnose_lgbm.py

Task 13.6 - why does is_new_device carry 58.65% of gain?

Task 10 measured is_new_device at 0.072 normal vs 0.140 fraud (1.95x,
the WEAKEST recorded signal). Task 12.5b did not place it in the top 15
single features. Task 13 ranks it #1 with 58.65% of total gain. Those
three facts need reconciling before the result is recorded.

Task 12.5b checked single features for perfect separation. It could not
see a PAIR of features that never co-occurs in normal traffic - which a
linear model cannot exploit but a tree exploits in one split pair.
That blind spot is what section 2 closes.

    python scripts/diagnose_lgbm.py
    python scripts/diagnose_lgbm.py --top-k 8 --ablation-rounds 4
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import typer
from sklearn.metrics import average_precision_score

from streamguard.ml.splitter import split, PROJECT_ROOT
from streamguard.ml.lgbm import LGBMModel, LGBMConfig
from streamguard.ml.metrics import per_pattern_recall
from streamguard.utils.logging_config import get_logger, setup_logging

app = typer.Typer(add_completion=False)
log = get_logger(__name__)

MODELS_DIR = PROJECT_ROOT / "models"
REPORTS_DIR = PROJECT_ROOT / "reports"
LINE = "=" * 72

# What Task 10 recorded, for direct comparison in section 1.
TASK10_IS_NEW_DEVICE_NORMAL = 0.072
TASK10_IS_NEW_DEVICE_FRAUD = 0.140


def binary_feature_report(X: pd.DataFrame, y: np.ndarray,
                          fraud_type: pd.Series, col: str) -> pd.DataFrame:
    """P(feature=1) for normals and for each fraud pattern.

    This is the direct comparison against the Task 10 table. If the
    numbers here differ from 0.072 / 0.140, the explanation lies in the
    data, not in the model.
    """
    x = X[col].to_numpy(dtype=float)
    yb = np.asarray(y).astype(bool)
    ft = pd.Series(fraud_type).reset_index(drop=True)

    rows = [{
        "group": "normal",
        "n": int((~yb).sum()),
        "mean": float(x[~yb].mean()),
    }, {
        "group": "ALL FRAUD",
        "n": int(yb.sum()),
        "mean": float(x[yb].mean()) if yb.any() else 0.0,
    }]
    for pat in sorted(ft[yb].dropna().unique()):
        m = yb & (ft == pat).to_numpy()
        rows.append({
            "group": str(pat),
            "n": int(m.sum()),
            "mean": float(x[m].mean()) if m.any() else 0.0,
        })
    return pd.DataFrame(rows)


def joint_purity(X: pd.DataFrame, y: np.ndarray, f1: str, f2: str,
                 bins: int = 10, min_fraud: int = 10) -> pd.DataFrame:
    """Cross-tabulate two features and look for cells that hold fraud
    but (almost) no legitimate traffic.

    A cell with many frauds and zero normals is a PERFECT SEPARATOR IN
    TWO DIMENSIONS. Invisible to the single-feature check at 12.5b,
    trivially exploitable by a tree.
    """
    def discretise(col: str) -> pd.Series:
        s = X[col]
        if s.nunique() <= 3:
            return s.astype(float).astype(str)
        try:
            return pd.qcut(s, bins, duplicates="drop").astype(str)
        except ValueError:
            return pd.cut(s, bins).astype(str)

    d = pd.DataFrame({
        f1: discretise(f1).to_numpy(),
        f2: discretise(f2).to_numpy(),
        "is_fraud": np.asarray(y).astype(int),
    })
    g = (d.groupby([f1, f2], observed=True)["is_fraud"]
           .agg(n="size", fraud="sum")
           .reset_index())
    g["normal"] = g["n"] - g["fraud"]
    g["fraud_rate"] = g["fraud"] / g["n"]
    return (g[g["fraud"] >= min_fraud]
            .sort_values("fraud_rate", ascending=False)
            .reset_index(drop=True))


@app.command()
def main(
    tag: str = typer.Option("v1"),
    top_k: int = typer.Option(6, help="How many top-gain features to examine"),
    ablation_rounds: int = typer.Option(3, help="Retrain rounds (~90s each)"),
    n_jobs: int = typer.Option(6),
    alerts_per_day: int = typer.Option(100),
) -> None:
    setup_logging()
    model_path = MODELS_DIR / f"lgbm_{tag}.txt"
    if not model_path.exists():
        print(f"ERROR: {model_path} not found. Run scripts/train_lgbm.py first.")
        raise typer.Exit(1)

    print(LINE)
    print("TASK 13.6 - INTERACTION LEAKAGE DIAGNOSTIC")
    print(LINE)

    blocks = split(save_manifest=False)
    train, val = blocks["train"], blocks["val"]
    val_days = val.day_range[1] - val.day_range[0] + 1
    k = alerts_per_day * val_days
    ft_train = (train.meta["fraud_type"] if "fraud_type" in train.meta.columns
                else pd.Series([None] * len(train.X)))
    ft_val = (val.meta["fraud_type"] if "fraud_type" in val.meta.columns
              else pd.Series([None] * len(val.X)))

    gain = LGBMModel.load(model_path).importance("gain")
    top = [f for f in gain["feature"].head(top_k) if f in train.X.columns]
    print()
    print(f"  top {len(top)} features by gain: {', '.join(top)}")

    # ---- 1. is_new_device against the Task 10 record ------------------
    print()
    print(LINE)
    print("1. IS_NEW_DEVICE - DATA vs THE TASK 10 RECORD")
    print(LINE)
    if "is_new_device" in train.X.columns:
        rep = binary_feature_report(train.X, train.y, ft_train, "is_new_device")
        print()
        print("  P(is_new_device = 1), computed on TRAIN:")
        print()
        print(rep.to_string(index=False, formatters={"mean": "{:.4f}".format}))
        print()
        print(f"  Task 10 recorded: normal {TASK10_IS_NEW_DEVICE_NORMAL:.3f}  "
              f"account_takeover {TASK10_IS_NEW_DEVICE_FRAUD:.3f}")
        norm = float(rep.loc[rep['group'] == 'normal', 'mean'].iloc[0])
        allf = float(rep.loc[rep['group'] == 'ALL FRAUD', 'mean'].iloc[0])
        print()
        if abs(norm - TASK10_IS_NEW_DEVICE_NORMAL) > 0.03:
            print("  !!  Normal rate differs from the Task 10 record. The")
            print("      Task 10 figure may have been measured differently.")
        ratio = allf / norm if norm else float("inf")
        print(f"  ALL FRAUD vs normal ratio: {ratio:.2f}x")
        if ratio < 3:
            print("      Weak on its own - consistent with Task 10. So its")
            print("      58.65% of gain must come from INTERACTION with")
            print("      another feature. Section 2 looks for that pair.")
        else:
            print("      Stronger than Task 10 suggested when measured across")
            print("      ALL fraud rather than account_takeover alone.")
    else:
        print("  is_new_device is not a column in this block.")

    # ---- 2. pairwise perfect separators -------------------------------
    print()
    print(LINE)
    print("2. TWO-FEATURE PURITY  (the 12.5b blind spot)")
    print(LINE)
    print("  Looking for cells holding fraud but little or no normal traffic.")
    print("  12.5b tested features ONE AT A TIME and found no perfect")
    print("  separator. A PAIR that never co-occurs legitimately would")
    print("  have been invisible to it.")

    findings = []
    pairs = [(a, b) for i, a in enumerate(top) for b in top[i + 1:]]
    for f1, f2 in pairs:
        g = joint_purity(train.X, train.y, f1, f2)
        if g.empty:
            continue
        worst = g.iloc[0]
        findings.append({
            "f1": f1, "f2": f2,
            "fraud": int(worst["fraud"]),
            "normal": int(worst["normal"]),
            "fraud_rate": float(worst["fraud_rate"]),
        })

    if not findings:
        print()
        print("  no cell held enough fraud to assess.")
    else:
        fd = (pd.DataFrame(findings)
              .sort_values("fraud_rate", ascending=False)
              .reset_index(drop=True))
        print()
        print("  highest fraud-rate cell for each pair (train):")
        print()
        print(fd.head(12).to_string(index=False,
                                    formatters={"fraud_rate": "{:.4f}".format}))
        print()
        perfect = fd[(fd["normal"] == 0) & (fd["fraud"] >= 10)]
        near = fd[(fd["fraud_rate"] >= 0.5) & (fd["normal"] > 0)]
        if len(perfect):
            print("  !!  PERFECT 2-D SEPARATOR FOUND.")
            print("      These pairs contain fraud and ZERO legitimate rows.")
            print("      That is a generator artefact, not a learned pattern.")
            print("      It must be named in the README and the report.")
            print()
            print(perfect.to_string(index=False))
        elif len(near):
            print("  Near-pure cells exist (fraud rate >= 50%) but normals are")
            print("  present. Strong interaction, not a hard separator.")
        else:
            print("  No pure or near-pure cell. The interaction is real but")
            print("  probabilistic - the model learned it, it was not given.")

    # ---- 3. tree ablation ---------------------------------------------
    print()
    print(LINE)
    print("3. TREE ABLATION  (12.5b repeated for LightGBM)")
    print(LINE)
    print("  Collapse after removing the top features -> they carry it.")
    print("  Score holds -> signal is distributed, as 12.5b concluded.")
    print()

    ablation = []
    dropped: list[str] = []
    for rnd in range(ablation_rounds + 1):
        cols = [c for c in train.X.columns if c not in set(dropped)]
        cfg = LGBMConfig(n_jobs=n_jobs, n_estimators=600)
        m = LGBMModel(cfg).fit(train.X[cols], train.y, val.X[cols], val.y)
        s = m.score_samples(val.X[cols])
        ap = float(average_precision_score(val.y, s))
        pp, ppn = per_pattern_recall(val.y, s, ft_val, k)
        geo = pp.get("geo_impossible", float("nan"))
        ato = pp.get("account_takeover", float("nan"))
        ablation.append({"round": rnd, "n_features": len(cols),
                         "dropped": list(dropped), "pr_auc": ap,
                         "geo_recall": geo, "ato_recall": ato})
        label = "none (full)" if not dropped else f"-{dropped[-1]}"
        print(f"  round {rnd}: {len(cols):>2} features  PR-AUC {ap:.4f}  "
              f"geo {geo * 100:>5.1f}%  ato {ato * 100:>5.1f}%   {label}")
        if rnd < ablation_rounds and rnd < len(top):
            dropped.append(top[rnd])

    # ---- verdict ------------------------------------------------------
    print()
    print(LINE)
    print("HOW TO READ THIS")
    print(LINE)
    first, last = ablation[0], ablation[-1]
    print(f"  full model          PR-AUC {first['pr_auc']:.4f}")
    print(f"  minus {len(last['dropped'])} features     PR-AUC {last['pr_auc']:.4f}")
    print()
    print("  A perfect 2-D cell in section 2 -> generator artefact, name it.")
    print("  No pure cell + graceful ablation -> the result stands, and")
    print("  'trees found an interaction a linear model could not' is a")
    print("  real, defensible finding.")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / f"task13_interaction_{tag}.json"
    out.write_text(json.dumps({
        "tag": tag,
        "top_features": top,
        "pair_findings": findings,
        "ablation": ablation,
    }, indent=2, default=float), encoding="utf-8")
    print()
    print(f"  saved: {out}")
    print(LINE)


if __name__ == "__main__":
    app()