"""
scripts/build_graph_features.py

Task 18A - add graph features to features.parquet.

Walks the existing feature file in CHRONOLOGICAL ORDER, building the
graph as it goes, so every row sees only the network as it stood
before that transaction. Same no-look-ahead rule as Task 10.

Writes a NEW file; the original is left untouched so the Task 12-17
results stay reproducible.

    python scripts/build_graph_features.py
"""

from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
import typer

from streamguard.ml.splitter import PROJECT_ROOT
from streamguard.features.graph import TransactionGraph, GRAPH_FEATURE_NAMES
from streamguard.utils.logging_config import get_logger, setup_logging

app = typer.Typer(add_completion=False)
log = get_logger(__name__)

PROCESSED = PROJECT_ROOT / "data" / "processed"
SOURCE = PROCESSED / "features.parquet"
OUTPUT = PROCESSED / "features_graph.parquet"
LINE = "=" * 72


@app.command()
def main(
    source: Path = typer.Option(SOURCE),
    output: Path = typer.Option(OUTPUT),
    ring_hops: int = typer.Option(2),
    ring_cap: int = typer.Option(200),
) -> None:
    setup_logging()
    print(LINE)
    print("TASK 18A - GRAPH FEATURES")
    print(LINE)

    if not source.exists():
        print(f"ERROR: {source} not found.")
        raise typer.Exit(1)

    print()
    print(f"  reading  {source}")
    df = pd.read_parquet(source)
    print(f"  {len(df):,} rows, {len(df.columns)} columns")

    needed = ["card_ref", "merchant_ref", "occurred_at", "transaction_ref"]
    missing = [c for c in needed if c not in df.columns]
    if missing:
        print(f"  ERROR: columns missing from the feature file: {missing}")
        print(f"  available: {sorted(df.columns)}")
        raise typer.Exit(1)

    # device_ref is not in the Task 10 feature file - the writer kept
    # only the derived is_new_device flag, not the raw id. The graph
    # needs the id itself to know WHICH device, so it is joined back
    # from the database on transaction_ref.
    if "device_ref" not in df.columns:
        print()
        print("  device_ref not in the feature file - joining from the database")
        from sqlalchemy import text
        from streamguard.db.session import get_session

        with get_session() as s:
            dev = pd.read_sql(
                text("""
                    SELECT t.transaction_ref, d.device_ref
                    FROM transactions t
                    LEFT JOIN devices d ON d.id = t.device_id
                """),
                s.connection(),
            )
        print(f"  joined {len(dev):,} rows from the database")
        df = df.merge(dev, on="transaction_ref", how="left")
        n_null = int(df["device_ref"].isna().sum())
        print(f"  device_ref present on {len(df) - n_null:,} rows, "
              f"null on {n_null:,}")
        print("  (a null device is normal - card-present POS transactions")
        print("   have no device, and those rows get 0 for device features)")

    # Chronological order is not optional - it IS the no-leakage
    # guarantee. The file is already sorted, but sorting again is cheap
    # insurance against a future change upstream.
    df = df.sort_values("occurred_at", kind="mergesort").reset_index(drop=True)

    graph = TransactionGraph(ring_hops=ring_hops, ring_cap=ring_cap)

    print()
    print("  walking rows in time order, building the graph as we go")
    print("  (a row sees only edges added by EARLIER rows)")
    print()

    rows = []
    t0 = time.perf_counter()
    cards = df["card_ref"].to_numpy()
    merchants = df["merchant_ref"].to_numpy()
    devices = df["device_ref"].to_numpy()
    times = df["occurred_at"].to_list()

    for i in range(len(df)):
        dev = devices[i]
        dev = None if (dev is None or pd.isna(dev)) else str(dev)
        rows.append(graph.process(str(cards[i]), str(merchants[i]),
                                  dev, times[i]))
        if (i + 1) % 100_000 == 0:
            rate = (i + 1) / (time.perf_counter() - t0)
            print(f"    {i + 1:>9,} / {len(df):,}  ({rate:,.0f}/s)")

    elapsed = time.perf_counter() - t0
    print(f"    {len(df):>9,} / {len(df):,}  done in {elapsed:.1f}s")

    gf = pd.DataFrame(rows, columns=GRAPH_FEATURE_NAMES).astype("float32")
    out_df = pd.concat([df.reset_index(drop=True), gf], axis=1)

    print()
    print(LINE)
    print("GRAPH SIZE")
    print(LINE)
    for k, v in graph.stats().items():
        print(f"  {k:<22} {v:>12,}")

    print()
    print(LINE)
    print("FEATURE SUMMARY (fraud vs normal)")
    print(LINE)
    print()
    if "is_fraud" in out_df.columns:
        y = out_df["is_fraud"].astype(bool)
        print(f"  {'feature':<28}{'normal':>12}{'fraud':>12}{'ratio':>10}")
        print("  " + "-" * 62)
        for c in GRAPH_FEATURE_NAMES:
            n = float(gf.loc[~y.to_numpy(), c].mean())
            f = float(gf.loc[y.to_numpy(), c].mean())
            ratio = (f / n) if n else float("inf") if f else 1.0
            print(f"  {c:<28}{n:>12.4f}{f:>12.4f}{ratio:>10.2f}")
        print()
        print("  A ratio near 1.0 means the feature carries no signal on")
        print("  its own. Trees may still use it in combination - check")
        print("  the importance after retraining.")

    nan = int(gf.isna().sum().sum())
    inf = int((~gf.apply(lambda s: s.abs() < 1e30)).sum().sum())
    print()
    print(f"  NaN: {nan}   inf: {inf}")

    out_df.to_parquet(output, index=False)
    size_mb = output.stat().st_size / 1_000_000

    print()
    print(LINE)
    print(f"  wrote {output}")
    print(f"  {len(out_df):,} rows, {len(out_df.columns)} columns, {size_mb:.1f} MB")
    print(f"  original file untouched: {source}")
    print(LINE)


if __name__ == "__main__":
    app()