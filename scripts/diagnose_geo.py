"""
scripts/diagnose_geo.py

Task 13.7B - why is distance_from_home_km a fraud marker, and why did
CNP implied_speed jump to 62,641 km/h?

Two questions:
  1. How are merchant distances distributed for normal vs each fraud
     pattern? (the 925 km vs 3.3 km artifact)
  2. For CNP rows with absurd implied speed, what was the PREVIOUS
     transaction on that card, and how far away?

Read-only.

    python scripts/diagnose_geo.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import typer

from streamguard.ml.splitter import split
from streamguard.utils.logging_config import setup_logging

app = typer.Typer(add_completion=False)
LINE = "=" * 72


@app.command()
def main(top: int = typer.Option(15)) -> None:
    setup_logging()
    print(LINE)
    print("TASK 13.7B - GEOGRAPHY DIAGNOSTIC")
    print(LINE)

    blocks = split(save_manifest=False)
    train = blocks["train"]
    X = train.X
    meta = train.meta.reset_index(drop=True)
    y = np.asarray(train.y).astype(bool)
    ft = meta["fraud_type"] if "fraud_type" in meta.columns else None

    # ---- 1. distance distribution -----------------------------------
    print()
    print(LINE)
    print("1. DISTANCE FROM HOME - percentiles")
    print(LINE)
    col = "distance_from_home_km"
    x = X[col].to_numpy(dtype=float)
    pcts = [10, 25, 50, 75, 90, 99]

    rows = [{"group": "normal", "n": int((~y).sum()),
             **{f"p{p}": float(np.percentile(x[~y], p)) for p in pcts}}]
    if ft is not None:
        for pat in sorted(ft[y].dropna().unique()):
            m = y & (ft == pat).to_numpy()
            if m.sum() == 0:
                continue
            rows.append({"group": str(pat), "n": int(m.sum()),
                         **{f"p{p}": float(np.percentile(x[m], p)) for p in pcts}})
    print()
    print(pd.DataFrame(rows).to_string(index=False,
                                       float_format=lambda v: f"{v:,.1f}"))
    print()
    print("  If fraud percentiles sit entirely above normal's p99, the")
    print("  merchant pools differ structurally - a geographic artifact.")

    # ---- 2. the CNP speed problem -----------------------------------
    print()
    print(LINE)
    print("2. IMPLIED SPEED - where does 62,641 km/h come from?")
    print(LINE)
    speed = X["implied_speed_kmh"].to_numpy(dtype=float)
    dist_prev = X["distance_from_prev_km"].to_numpy(dtype=float)
    secs = X["seconds_since_prev"].to_numpy(dtype=float)

    if ft is not None:
        cnp = y & (ft == "card_not_present").to_numpy()
        if cnp.sum():
            print()
            print(f"  card_not_present rows: {int(cnp.sum()):,}")
            print()
            d = pd.DataFrame({
                "implied_speed_kmh": speed[cnp],
                "distance_from_prev_km": dist_prev[cnp],
                "seconds_since_prev": secs[cnp],
            })
            print(d.describe(percentiles=[0.25, 0.5, 0.75, 0.95])
                   .to_string(float_format=lambda v: f"{v:,.2f}"))
            print()
            worst = d.sort_values("implied_speed_kmh", ascending=False).head(top)
            print(f"  the {top} fastest CNP rows:")
            print()
            print(worst.to_string(index=False,
                                  float_format=lambda v: f"{v:,.2f}"))
            print()
            tiny = (d["seconds_since_prev"] < 5).mean()
            print(f"  fraction with seconds_since_prev < 5 : {tiny:.1%}")
            print("  A near-zero time gap divides into a huge speed even")
            print("  when the distance is small. That is the mechanism to")
            print("  check first.")

    # ---- 3. normal traffic for comparison ----------------------------
    print()
    print(LINE)
    print("3. NORMAL TRAFFIC, same three columns")
    print(LINE)
    print()
    dn = pd.DataFrame({
        "implied_speed_kmh": speed[~y],
        "distance_from_prev_km": dist_prev[~y],
        "seconds_since_prev": secs[~y],
    })
    print(dn.describe(percentiles=[0.5, 0.95, 0.99])
            .to_string(float_format=lambda v: f"{v:,.2f}"))

    print()
    print(LINE)


if __name__ == "__main__":
    app()