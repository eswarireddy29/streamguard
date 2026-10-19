"""
src/streamguard/ml/splitter.py

Task 12.2 - temporal train / validation / test split.

THE GOVERNING RULE OF THIS MODULE:
    every row in TRAIN happened strictly before every row in VAL,
    and every row in VAL happened strictly before every row in TEST.

No random shuffling anywhere. No row appears in two blocks.
Features and labels are returned as separate objects so that passing
the label in as a feature is not something you can do by accident.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np
import pandas as pd

from streamguard.features.computer import FEATURE_NAMES
from streamguard.utils.logging_config import get_logger

log = get_logger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
FEATURES_PATH = PROJECT_ROOT / "data" / "processed" / "features.parquet"
MANIFEST_PATH = PROJECT_ROOT / "data" / "processed" / "split_manifest.json"
TEST_ACCESS_LOG = PROJECT_ROOT / "data" / "processed" / "test_set_access.log"

IST = "Asia/Kolkata"

# Columns that must NEVER reach the model as input.
# is_fraud / fraud_type are the answer. The rest are identifiers or
# timestamps - a model that learns from a row id has learned nothing.
FORBIDDEN_AS_FEATURES = {
    "is_fraud",
    "fraud_type",
    "transaction_ref",
    "offset",
    "occurred_at",
    "ingested_at",
    "produced_at",
    "card_id",
    "customer_id",
    "merchant_id",
    "device_id",
    "id",
}

TRAIN_DAYS = 63   # simulation days 1-63   -> index 0..62
VAL_DAYS = 13     # simulation days 64-76  -> index 63..75
# remainder is test                        -> index 76..end


class ColumnNotFound(KeyError):
    """Raised when an expected column is absent, listing what IS there."""


@dataclass(frozen=True)
class SplitManifest:
    """A written record of exactly how the data was divided.

    Saved to JSON so Task 13, Task 15 and the report all refer to the
    same boundaries. If this file and the code ever disagree, you have
    a reproducibility bug and you want to find out loudly.
    """
    features_path: str
    n_rows_total: int
    timestamp_column: str
    timezone_aware: bool
    first_event_local: str
    last_event_local: str
    n_days: int
    train_day_range: tuple[int, int]
    val_day_range: tuple[int, int]
    test_day_range: tuple[int, int]
    train_rows: int
    val_rows: int
    test_rows: int
    train_fraud: int
    val_fraud: int
    test_fraud: int
    n_features: int
    created_at: str

    def save(self, path: Path = MANIFEST_PATH) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        return path


@dataclass
class Block:
    """One slice of the data: features, label, and the metadata columns."""
    name: str
    X: pd.DataFrame          # features only - 49 columns, nothing else
    y: np.ndarray            # 0 / 1 labels
    meta: pd.DataFrame       # timestamps, refs, fraud_type - for analysis
    day_range: tuple[int, int]

    def __len__(self) -> int:
        return len(self.X)

    @property
    def n_fraud(self) -> int:
        return int(self.y.sum())

    @property
    def prevalence(self) -> float:
        """Fraction of rows that are fraud. This is the PR-AUC a random
        model scores - the number every result must be read against."""
        return float(self.y.mean()) if len(self.y) else 0.0

    def describe(self) -> str:
        return (f"{self.name:<6} days {self.day_range[0]:>2}-{self.day_range[1]:<2}  "
                f"rows {len(self):>8,}  fraud {self.n_fraud:>5,}  "
                f"prevalence {self.prevalence * 100:.3f}%")


def resolve_column(df_or_cols, candidates: list[str], purpose: str) -> str:
    """Return the first candidate name present, else fail loudly.

    Written this way because column names were decided in Task 10 and
    this module should adapt to them rather than assume them. A wrong
    guess that silently returns None would be a silent bug, which is
    the failure mode this project keeps running into.
    """
    cols = list(df_or_cols.columns) if hasattr(df_or_cols, "columns") else list(df_or_cols)
    for c in candidates:
        if c in cols:
            return c
    raise ColumnNotFound(
        f"Could not find a column for '{purpose}'. "
        f"Tried {candidates}. Available columns: {sorted(cols)}"
    )


def load_features(path: Path = FEATURES_PATH) -> pd.DataFrame:
    """Read the whole feature file into memory.

    Memory note for an 8 GB machine: 791k rows x 49 float64 features is
    about 310 MB. We downcast the feature columns to float32 below,
    halving that to ~155 MB. float32 carries ~7 significant digits,
    which is far more than these features need.
    """
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Build it with: python scripts/build_features.py"
        )
    log.info("loading_features", path=str(path))
    df = pd.read_parquet(path)
    log.info("features_loaded", rows=len(df), columns=len(df.columns))
    return df


def add_day_index(df: pd.DataFrame, timestamp_col: str | None = None
                  ) -> tuple[pd.DataFrame, str, bool]:
    """Add a 0-based '_day' column derived from LOCAL (IST) midnight.

    Why local and not UTC: the business day a transaction belongs to is
    the one the customer experienced. Splitting on UTC midnight would
    put 00:00-05:30 IST into the previous day, which shifts every
    boundary by 5h30m - exactly the class of bug that hit Task 6.
    """
    df = df.copy()
    tcol = timestamp_col or resolve_column(
        df, ["occurred_at", "event_time", "timestamp"], "event time"
    )
    ts = pd.to_datetime(df[tcol])
    aware = ts.dt.tz is not None
    local = ts.dt.tz_convert(IST) if aware else ts

    midnight = local.dt.normalize()
    df["_day"] = (midnight - midnight.min()).dt.days.astype("int32")
    df["_local_time"] = local
    return df, tcol, aware


def _make_block(df: pd.DataFrame, name: str, lo: int, hi: int,
                feature_cols: list[str], label_col: str) -> Block:
    mask = (df["_day"] >= lo) & (df["_day"] <= hi)
    sub = df.loc[mask]

    # Sort by time so that "the last row" means the latest event.
    # Ordering matters for any time-aware diagnostic later.
    sub = sub.sort_values("_local_time", kind="mergesort")

    X = sub[feature_cols].astype("float32")
    y = sub[label_col].to_numpy().astype(np.int8)

    meta_cols = [c for c in sub.columns if c not in set(feature_cols)]
    meta = sub[meta_cols]

    return Block(name=name, X=X, y=y, meta=meta, day_range=(lo, hi))


def split(path: Path = FEATURES_PATH,
          train_days: int = TRAIN_DAYS,
          val_days: int = VAL_DAYS,
          save_manifest: bool = True) -> dict[str, Block]:
    """Split the feature file into train / val / test by calendar day.

    Returns a dict with keys 'train' and 'val'. TEST IS NOT RETURNED -
    call load_test() with a written reason if you genuinely need it.
    """
    raw = load_features(path)
    df, tcol, aware = add_day_index(raw)

    label_col = resolve_column(df, ["is_fraud", "label", "y"], "fraud label")

    present = set(df.columns)
    feature_cols = [c for c in FEATURE_NAMES if c in present]
    missing = [c for c in FEATURE_NAMES if c not in present]
    if missing:
        raise ColumnNotFound(
            f"FEATURE_NAMES declares columns absent from the file: {missing}"
        )

    # Hard guarantee: no forbidden column can be a feature.
    overlap = set(feature_cols) & FORBIDDEN_AS_FEATURES
    if overlap:
        raise ValueError(
            f"FEATURE_NAMES contains forbidden columns: {sorted(overlap)}. "
            "A label or identifier must never be a model input."
        )

    last_day = int(df["_day"].max())
    train_hi = train_days - 1
    val_hi = train_hi + val_days
    if val_hi >= last_day:
        raise ValueError(
            f"Not enough days: train_days={train_days} + val_days={val_days} "
            f"leaves no test block (last day index {last_day})."
        )

    ranges = {
        "train": (0, train_hi),
        "val": (train_hi + 1, val_hi),
        "test": (val_hi + 1, last_day),
    }

    blocks = {
        name: _make_block(df, name, lo, hi, feature_cols, label_col)
        for name, (lo, hi) in ranges.items()
    }

    # Invariant checks. These are cheap and they run every single time.
    total = sum(len(b) for b in blocks.values())
    if total != len(df):
        raise AssertionError(f"blocks hold {total} rows, file has {len(df)}")

    t_max = blocks["train"].meta["_local_time"].max()
    v_min = blocks["val"].meta["_local_time"].min()
    v_max = blocks["val"].meta["_local_time"].max()
    s_min = blocks["test"].meta["_local_time"].min()
    if not (t_max < v_min and v_max < s_min):
        raise AssertionError("blocks are not strictly ordered in time")

    for b in blocks.values():
        log.info("block", summary=b.describe())

    if save_manifest:
        SplitManifest(
            features_path=str(path),
            n_rows_total=len(df),
            timestamp_column=tcol,
            timezone_aware=aware,
            first_event_local=str(df["_local_time"].min()),
            last_event_local=str(df["_local_time"].max()),
            n_days=last_day + 1,
            train_day_range=ranges["train"],
            val_day_range=ranges["val"],
            test_day_range=ranges["test"],
            train_rows=len(blocks["train"]),
            val_rows=len(blocks["val"]),
            test_rows=len(blocks["test"]),
            train_fraud=blocks["train"].n_fraud,
            val_fraud=blocks["val"].n_fraud,
            test_fraud=blocks["test"].n_fraud,
            n_features=len(feature_cols),
            created_at=dt.datetime.now().isoformat(timespec="seconds"),
        ).save()

    # Deliberately withhold test from the normal return value.
    return {"train": blocks["train"], "val": blocks["val"]}


def load_test(reason: str, path: Path = FEATURES_PATH,
              train_days: int = TRAIN_DAYS, val_days: int = VAL_DAYS) -> Block:
    """Return the TEST block. Requires a written reason, which is logged.

    The test set is only an honest estimate while it is untouched. Each
    look-then-adjust cycle fits you to it a little. This does not block
    you - it makes the number of accesses countable. If this log has
    many entries by Task 15, say so in the report.
    """
    if not reason or len(reason.strip()) < 10:
        raise ValueError(
            "load_test() requires a written reason of at least 10 characters, "
            "e.g. load_test('Task 15 final held-out evaluation')"
        )

    raw = load_features(path)
    df, _, _ = add_day_index(raw)
    label_col = resolve_column(df, ["is_fraud", "label", "y"], "fraud label")
    present = set(df.columns)
    feature_cols = [c for c in FEATURE_NAMES if c in present]

    last_day = int(df["_day"].max())
    lo = train_days + val_days
    block = _make_block(df, "test", lo, last_day, feature_cols, label_col)

    TEST_ACCESS_LOG.parent.mkdir(parents=True, exist_ok=True)
    with TEST_ACCESS_LOG.open("a", encoding="utf-8") as fh:
        fh.write(f"{dt.datetime.now().isoformat(timespec='seconds')}\t{reason.strip()}\n")

    n_prev = sum(1 for _ in TEST_ACCESS_LOG.read_text(encoding="utf-8").splitlines())
    log.warning("test_set_accessed", reason=reason, total_accesses=n_prev)
    return block