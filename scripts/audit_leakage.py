"""
scripts/audit_leakage.py

Task 13.7A - find every feature that acts as a label proxy.

We found is_new_device by accident, through a feature-importance
oddity: four of five fraud patterns had it set to exactly 1.0000 on
every single row. That is the generator marking its own fraud, not a
behaviour the model learned.

There may be others. This script checks EVERY feature against EVERY
pattern and flags three failure modes:

  CONSTANT  - a pattern takes one single value on all its rows
  DISJOINT  - a pattern's value range never overlaps normal traffic
  EXTREME   - a pattern sits far outside normal's central range

Read-only. Touches TRAIN only; test is never loaded.

    python scripts/audit_leakage.py
    python scripts/audit_leakage.py --min-rows 50
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import typer

from streamguard.ml.splitter import split, PROJECT_ROOT
from streamguard.utils.logging_config import get_logger, setup_logging

app = typer.Typer(add_completion=False)
log = get_logger(__name__)

REPORTS_DIR = PROJECT_ROOT / "reports"
LINE = "=" * 72


def audit_feature(x: np.ndarray, is_fraud: np.ndarray,
                  pattern_mask: np.ndarray, col: str, pattern: str) -> dict:
    """Compare one feature's behaviour on one pattern vs normal traffic."""
    normal = x[~is_fraud]
    pat = x[pattern_mask]
    if len(pat) == 0 or len(normal) == 0:
        return {}

    uniq = np.unique(pat)
    constant = len(uniq) == 1

    # Does the pattern's range overlap normal's range at all?
    disjoint = (pat.min() > normal.max()) or (pat.max() < normal.min())

    # How far outside normal's middle 99% does the pattern's median sit?
    lo, hi = np.percentile(normal, [0.5, 99.5])
    med = float(np.median(pat))
    extreme = med < lo or med > hi

    # P(feature = 1) for binary features; mean ratio otherwise.
    binary = set(np.unique(x)).issubset({0.0, 1.0})

    verdict = "ok"
    if constant and binary and float(uniq[0]) in (0.0, 1.0):
        # A binary feature pinned to one value on every row of a pattern
        # is the exact is_new_device failure.
        p_normal = float(normal.mean())
        if abs(float(uniq[0]) - p_normal) > 0.5:
            verdict = "CONSTANT"
    elif constant:
        verdict = "CONSTANT"
    elif disjoint:
        verdict = "DISJOINT"
    elif extreme:
        verdict = "EXTREME"

    return {
        "feature": col,
        "pattern": pattern,
        "n": int(len(pat)),
        "binary": binary,
        "pattern_mean": float(pat.mean()),
        "normal_mean": float(normal.mean()),
        "pattern_unique_values": int(len(uniq)),
        "pattern_min": float(pat.min()),
        "pattern_max": float(pat.max()),
        "normal_min": float(normal.min()),
        "normal_max": float(normal.max()),
        "verdict": verdict,
    }


@app.command()
def main(
    min_rows: int = typer.Option(30, help="Skip patterns with fewer rows"),
) -> None:
    setup_logging()
    print(LINE)
    print("TASK 13.7A - LABEL PROXY AUDIT")
    print(LINE)

    blocks = split(save_manifest=False)
    train = blocks["train"]
    X, y = train.X, train.y
    if "fraud_type" not in train.meta.columns:
        print("ERROR: fraud_type not in metadata - cannot audit per pattern.")
        raise typer.Exit(1)

    ft = train.meta["fraud_type"].reset_index(drop=True)
    is_fraud = np.asarray(y).astype(bool)
    patterns = sorted(ft[is_fraud].dropna().unique())

    print()
    print(f"  {len(X):,} training rows, {int(is_fraud.sum()):,} fraud, "
          f"{X.shape[1]} features, {len(patterns)} patterns")

    findings = []
    for col in X.columns:
        x = X[col].to_numpy(dtype=float)
        x = np.nan_to_num(x, nan=0.0, posinf=0.0, neginf=0.0)
        for pat in patterns:
            mask = is_fraud & (ft == pat).to_numpy()
            if mask.sum() < min_rows:
                continue
            res = audit_feature(x, is_fraud, mask, col, str(pat))
            if res and res["verdict"] != "ok":
                findings.append(res)

    fd = pd.DataFrame(findings)

    # ---- 1. CONSTANT: the is_new_device failure mode -------------------
    print()
    print(LINE)
    print("1. CONSTANT  - a pattern takes ONE value on every row")
    print(LINE)
    print("  This is the is_new_device failure: the generator marks its")
    print("  own fraud. Each of these is a label proxy the model can read")
    print("  directly instead of learning behaviour.")
    print()
    const = fd[fd["verdict"] == "CONSTANT"] if len(fd) else pd.DataFrame()
    if len(const) == 0:
        print("  none.")
    else:
        view = const[["feature", "pattern", "n", "pattern_mean", "normal_mean"]]
        print(view.to_string(index=False,
                             formatters={"pattern_mean": "{:.4f}".format,
                                         "normal_mean": "{:.4f}".format}))
        print()
        worst = (const.groupby("feature")["pattern"].count()
                 .sort_values(ascending=False))
        print("  features affected, by how many patterns they leak in:")
        for feat, n in worst.items():
            print(f"      {feat:<28} {n} of {len(patterns)} patterns")

    # ---- 2. DISJOINT ---------------------------------------------------
    print()
    print(LINE)
    print("2. DISJOINT  - pattern's range never overlaps normal traffic")
    print(LINE)
    dis = fd[fd["verdict"] == "DISJOINT"] if len(fd) else pd.DataFrame()
    if len(dis) == 0:
        print("  none.")
    else:
        print(dis[["feature", "pattern", "n", "pattern_min", "pattern_max",
                   "normal_min", "normal_max"]]
              .to_string(index=False, float_format=lambda v: f"{v:,.2f}"))

    # ---- 3. EXTREME ----------------------------------------------------
    print()
    print(LINE)
    print("3. EXTREME  - pattern's median outside normal's middle 99%")
    print(LINE)
    print("  NOT automatically a bug. Real fraud IS extreme on some")
    print("  features - that is the whole signal. Listed for judgement,")
    print("  not condemnation. The question for each: would this be")
    print("  extreme in the real world, or only because I made it so?")
    print()
    ext = fd[fd["verdict"] == "EXTREME"] if len(fd) else pd.DataFrame()
    if len(ext) == 0:
        print("  none.")
    else:
        print(ext[["feature", "pattern", "n", "pattern_mean", "normal_mean"]]
              .head(30)
              .to_string(index=False, float_format=lambda v: f"{v:,.3f}"))
        if len(ext) > 30:
            print(f"  ... and {len(ext) - 30} more (see the JSON)")

    # ---- 4. the two known shortcuts, in detail -------------------------
    print()
    print(LINE)
    print("4. THE TWO KNOWN SHORTCUTS, PER PATTERN")
    print(LINE)
    for col in ("is_new_device", "distance_from_home_km"):
        if col not in X.columns:
            print(f"  {col}: not a column")
            continue
        x = X[col].to_numpy(dtype=float)
        rows = [{"group": "normal", "n": int((~is_fraud).sum()),
                 "mean": float(x[~is_fraud].mean()),
                 "median": float(np.median(x[~is_fraud])),
                 "unique": int(len(np.unique(x[~is_fraud])))}]
        for pat in patterns:
            m = is_fraud & (ft == pat).to_numpy()
            rows.append({"group": str(pat), "n": int(m.sum()),
                         "mean": float(x[m].mean()),
                         "median": float(np.median(x[m])),
                         "unique": int(len(np.unique(x[m])))})
        print()
        print(f"  {col}:")
        print(pd.DataFrame(rows).to_string(
            index=False, float_format=lambda v: f"{v:,.3f}"))
        print("  ('unique' = 1 means every row of that pattern is identical)")

    # ---- verdict -------------------------------------------------------
    print()
    print(LINE)
    print("WHAT TO FIX")
    print(LINE)
    n_const = len(const)
    print(f"  CONSTANT findings : {n_const}   <- these are bugs, fix them")
    print(f"  DISJOINT findings : {len(dis)}   <- probably bugs, judge each")
    print(f"  EXTREME findings  : {len(ext)}   <- judgement call, not automatic")
    print()
    print("  A fraud pattern should SHIFT a feature's distribution, never")
    print("  pin it to a constant. Pinning is the generator telling the")
    print("  model the answer.")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / "task13_leakage_audit.json"
    out.write_text(json.dumps({
        "n_patterns": len(patterns),
        "patterns": [str(p) for p in patterns],
        "findings": findings,
    }, indent=2, default=float), encoding="utf-8")
    print()
    print(f"  saved: {out}")
    print(LINE)


if __name__ == "__main__":
    app()