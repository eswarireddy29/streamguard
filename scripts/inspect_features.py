"""
scripts/inspect_features.py

Task 12, Step 1 - look at data/processed/features.parquet before splitting it.
Read-only. Touches nothing, writes nothing, changes nothing.

Run from the project root with the venv active:
    python scripts/inspect_features.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

# FEATURE_NAMES is the ordered column contract from Task 10.
# Imported so we can cross-check it against what is actually in the file.
try:
    from streamguard.features.computer import FEATURE_NAMES
except Exception as exc:  # pragma: no cover
    print(f"WARNING: could not import FEATURE_NAMES ({exc})")
    FEATURE_NAMES = []

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = PROJECT_ROOT / "data" / "processed" / "features.parquet"

IST = "Asia/Kolkata"

# The proposed split, as day indexes counting from 0.
# Day 1 of the simulation is index 0, so days 1-63 are indexes 0..62.
TRAIN_LAST_DAY_IDX = 62   # days 1-63
VAL_LAST_DAY_IDX = 75     # days 64-76
# everything after that is test            # days 77-90

LINE = "=" * 72


def section(title: str) -> None:
    print()
    print(LINE)
    print(title)
    print(LINE)


def main(path: Path) -> int:
    if not path.exists():
        print(f"ERROR: feature file not found at {path}")
        print("Rebuild it with:  python scripts/build_features.py")
        return 1

    # 1. File-level facts, read from the Parquet header only.
    #    No row data is loaded here.
    pf = pq.ParquetFile(path)
    schema = pf.schema_arrow
    n_rows = pf.metadata.num_rows

    section("1. FILE")
    print(f"  path         : {path}")
    print(f"  rows         : {n_rows:,}")
    print(f"  columns      : {len(schema.names)}")
    print(f"  row groups   : {pf.metadata.num_row_groups}")
    print(f"  size on disk : {path.stat().st_size / 1_000_000:.1f} MB")

    # 2. Every column and its exact Arrow type.
    section("2. COLUMNS")
    for i, field in enumerate(schema):
        print(f"  {i:>3}  {field.name:<34}  {field.type}")

    # 3. Cross-check against the Task 10 feature contract.
    #    Anything in the file but NOT in FEATURE_NAMES is metadata
    #    or a label - those are the columns the model must never see.
    file_cols = list(schema.names)
    feature_set = set(FEATURE_NAMES)
    non_feature = [c for c in file_cols if c not in feature_set]
    declared_missing = [c for c in FEATURE_NAMES if c not in set(file_cols)]

    section("3. FEATURE CONTRACT")
    print(f"  FEATURE_NAMES declares      : {len(FEATURE_NAMES)} features")
    print(f"  of those, present in file   : {len(FEATURE_NAMES) - len(declared_missing)}")
    print(f"  declared but MISSING        : {declared_missing or 'none'}")
    print(f"  non-feature columns ({len(non_feature)}):")
    for c in non_feature:
        print(f"      {c}")

    # 4. Find the timestamp column and check its timezone status.
    ts_cols = [f.name for f in schema if pa.types.is_timestamp(f.type)]
    section("4. TIMESTAMP")
    print(f"  timestamp-typed columns: {ts_cols or 'NONE FOUND'}")

    if not ts_cols:
        print("  ERROR: no timestamp column. Cannot split by time.")
        return 1

    # Prefer occurred_at - when it HAPPENED, not when we stored it.
    tcol = "occurred_at" if "occurred_at" in ts_cols else ts_cols[0]
    print(f"  using column           : {tcol}")
    if tcol != "occurred_at":
        print("  WARNING: this is NOT occurred_at. Check this before splitting.")

    # Load only the few small columns we need. Not the 49 feature
    # columns - that is what keeps memory low on an 8 GB machine.
    wanted = [c for c in (tcol, "is_fraud", "fraud_type", "offset",
                          "transaction_ref", "amount") if c in file_cols]
    df = pd.read_parquet(path, columns=wanted)
    print(f"  loaded {len(df):,} rows x {len(wanted)} columns for inspection")

    ts = df[tcol]
    aware = ts.dt.tz is not None
    print(f"  timezone-aware         : {aware}  ({ts.dt.tz if aware else 'naive'})")

    if aware:
        local = ts.dt.tz_convert(IST)
        print(f"  converted to           : {IST}")
    else:
        # Naive. We do NOT guess. We read it as-is and let the
        # hour histogram below tell us whether it is already IST.
        local = ts
        print("  naive timestamps: reading as-is, NOT assuming UTC")

    print(f"  first                  : {local.min()}")
    print(f"  last                   : {local.max()}")
    print(f"  span                   : {(local.max() - local.min()).days} days")

    # 5. Hour histogram - the timezone sanity check.
    #    Task 6 verified: peak 19:00, trough 04:00, 18.3x between them.
    #    If the peak is not 19, the timestamps are NOT being read as IST.
    hours = local.dt.hour.value_counts().sort_index()
    busiest = hours.idxmax()
    quietest = hours.idxmin()

    section("5. TIMEZONE SANITY CHECK")
    print("  top 3 busiest hours:")
    for h, n in hours.sort_values(ascending=False).head(3).items():
        print(f"      {h:02d}:00   {n:>8,}")
    print(f"  quietest hour  : {quietest:02d}:00   {hours.min():>8,}")
    print(f"  peak / trough  : {hours.max() / hours.min():.1f}x")
    print()
    if busiest == 19:
        print("  OK  peak at 19:00 -- matches the Task 6 verified curve.")
    else:
        print(f"  !!  peak at {busiest:02d}:00, expected 19:00.")
        print("      Timestamps are not being read as IST. STOP and tell me.")

    # 6. Day index, then the proposed split.
    #    Day index 0 = the first calendar day present, in local time.
    midnight = local.dt.normalize()
    day_idx = (midnight - midnight.min()).dt.days
    df["_day"] = day_idx

    per_day = df.groupby("_day").agg(
        rows=("_day", "size"),
        fraud=("is_fraud", "sum") if "is_fraud" in df.columns else ("_day", "size"),
    )

    section("6. PER-DAY SHAPE")
    print(f"  distinct days : {per_day.shape[0]}")
    print(f"  rows per day  : min {per_day['rows'].min():,}  "
          f"mean {per_day['rows'].mean():,.0f}  max {per_day['rows'].max():,}")
    print()
    print("  first 3 days and last 3 days:")
    print("     day_idx     rows    fraud")
    for d, r in pd.concat([per_day.head(3), per_day.tail(3)]).iterrows():
        print(f"     {d:>7}  {int(r['rows']):>7,}  {int(r['fraud']):>7,}")

    # 7. The proposed split, measured rather than assumed.
    def block(lo: int, hi: int) -> tuple[int, int]:
        m = (df["_day"] >= lo) & (df["_day"] <= hi)
        rows = int(m.sum())
        fraud = int(df.loc[m, "is_fraud"].sum()) if "is_fraud" in df.columns else 0
        return rows, fraud

    last_day = int(df["_day"].max())
    blocks = [
        ("TRAIN", 0, TRAIN_LAST_DAY_IDX),
        ("VAL  ", TRAIN_LAST_DAY_IDX + 1, VAL_LAST_DAY_IDX),
        ("TEST ", VAL_LAST_DAY_IDX + 1, last_day),
    ]

    section("7. PROPOSED SPLIT  (day indexes, 0-based)")
    print("   block   days        rows      % rows    fraud   fraud %")
    total = len(df)
    for name, lo, hi in blocks:
        rows, fraud = block(lo, hi)
        pct = 100 * rows / total if total else 0
        fpct = 100 * fraud / rows if rows else 0
        print(f"   {name}  {lo:>3}-{hi:<3}  {rows:>9,}  {pct:>7.1f}%  "
              f"{fraud:>7,}  {fpct:>7.3f}%")

    covered = sum(block(lo, hi)[0] for _, lo, hi in blocks)
    print()
    print(f"   rows covered by the three blocks: {covered:,} of {total:,}")
    if covered != total:
        print("   !!  blocks do not cover every row. Tell me.")

    # 8. Per-pattern fraud counts inside each block - this decides
    #    whether per-pattern recall is measurable at Task 15.
    if "fraud_type" in df.columns:
        section("8. FRAUD PATTERNS PER BLOCK")
        patterns = sorted(p for p in df["fraud_type"].dropna().unique())
        header = "   pattern".ljust(26) + "".join(n.strip().rjust(10) for n, _, _ in blocks)
        print(header)
        for p in patterns:
            row = f"   {p}".ljust(26)
            for _, lo, hi in blocks:
                m = (df["_day"] >= lo) & (df["_day"] <= hi) & (df["fraud_type"] == p)
                row += f"{int(m.sum()):>10,}"
            print(row)

    print()
    print(LINE)
    print("Inspection complete. Nothing was modified.")
    print(LINE)
    return 0


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PATH
    raise SystemExit(main(target))