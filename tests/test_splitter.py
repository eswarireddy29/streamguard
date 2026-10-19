"""
tests/test_splitter.py

Task 12.6 - the split's guarantees, as PASS/FAIL.

These build small synthetic frames rather than reading the real
feature file, so the whole file runs in well under a second and is
not skipped on a fresh clone.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from streamguard.ml.splitter import (
    add_day_index, resolve_column, ColumnNotFound,
    FORBIDDEN_AS_FEATURES, _make_block,
)
from streamguard.features.computer import FEATURE_NAMES

IST = "Asia/Kolkata"


@pytest.fixture
def synthetic() -> pd.DataFrame:
    """20 days, 50 rows per day, timezone-aware IST timestamps."""
    rng = np.random.default_rng(42)
    rows = []
    start = pd.Timestamp("2026-01-01 00:00:00", tz=IST)
    for day in range(20):
        for i in range(50):
            rows.append({
                "occurred_at": start + pd.Timedelta(days=day, minutes=i * 17),
                "transaction_ref": f"T{day:03d}{i:03d}",
                "is_fraud": int(rng.random() < 0.05),
                "fraud_type": None,
                "feat_a": float(rng.normal()),
                "feat_b": float(rng.normal()),
            })
    return pd.DataFrame(rows)


class TestDayIndex:
    def test_day_index_is_zero_based(self, synthetic):
        df, _, _ = add_day_index(synthetic)
        assert df["_day"].min() == 0
        assert df["_day"].max() == 19

    def test_day_index_uses_local_midnight(self):
        """A 02:00 IST event belongs to its own IST day, not the one before.

        In UTC that instant is 20:30 the previous day. If the splitter
        used UTC midnight, this row would land in the wrong block - the
        same +5:30 displacement that hit the Task 6 generator.
        """
        df = pd.DataFrame({
            "occurred_at": [
                pd.Timestamp("2026-01-01 23:00:00", tz=IST),
                pd.Timestamp("2026-01-02 02:00:00", tz=IST),
            ],
            "is_fraud": [0, 0],
        })
        out, _, aware = add_day_index(df)
        assert aware is True
        assert list(out["_day"]) == [0, 1]

    def test_rows_within_a_day_share_an_index(self, synthetic):
        df, _, _ = add_day_index(synthetic)
        counts = df.groupby("_day").size()
        assert set(counts.unique()) == {50}


class TestBlocks:
    def _blocks(self, synthetic, train_hi=11, val_hi=15):
        df, _, _ = add_day_index(synthetic)
        cols = ["feat_a", "feat_b"]
        return {
            "train": _make_block(df, "train", 0, train_hi, cols, "is_fraud"),
            "val": _make_block(df, "val", train_hi + 1, val_hi, cols, "is_fraud"),
            "test": _make_block(df, "test", val_hi + 1, 19, cols, "is_fraud"),
        }

    def test_blocks_cover_every_row_exactly_once(self, synthetic):
        b = self._blocks(synthetic)
        assert sum(len(x) for x in b.values()) == len(synthetic)

    def test_no_transaction_appears_in_two_blocks(self, synthetic):
        b = self._blocks(synthetic)
        refs = [set(x.meta["transaction_ref"]) for x in b.values()]
        assert refs[0] & refs[1] == set()
        assert refs[1] & refs[2] == set()
        assert refs[0] & refs[2] == set()

    def test_blocks_are_strictly_ordered_in_time(self, synthetic):
        """THE DECISIVE TEST. Every training row must predate every
        validation row, and every validation row every test row. If this
        fails, the model is reading the future."""
        b = self._blocks(synthetic)
        assert b["train"].meta["_local_time"].max() < b["val"].meta["_local_time"].min()
        assert b["val"].meta["_local_time"].max() < b["test"].meta["_local_time"].min()

    def test_X_contains_no_forbidden_column(self, synthetic):
        b = self._blocks(synthetic)
        for block in b.values():
            assert set(block.X.columns) & FORBIDDEN_AS_FEATURES == set()

    def test_label_is_not_in_X(self, synthetic):
        b = self._blocks(synthetic)
        assert "is_fraud" not in b["train"].X.columns
        assert "fraud_type" not in b["train"].X.columns

    def test_rows_inside_a_block_are_chronological(self, synthetic):
        b = self._blocks(synthetic)
        t = b["train"].meta["_local_time"]
        assert t.is_monotonic_increasing

    def test_X_and_y_stay_aligned(self, synthetic):
        b = self._blocks(synthetic)["train"]
        assert len(b.X) == len(b.y)
        assert b.n_fraud == int(b.y.sum())

    def test_features_are_float32(self, synthetic):
        """float32 halves memory vs float64 - matters on 8 GB."""
        b = self._blocks(synthetic)["train"]
        assert all(str(d) == "float32" for d in b.X.dtypes)

    def test_split_is_deterministic(self, synthetic):
        a = self._blocks(synthetic)
        c = self._blocks(synthetic)
        for k in a:
            assert list(a[k].meta["transaction_ref"]) == list(c[k].meta["transaction_ref"])


class TestResolveColumn:
    def test_finds_first_present_candidate(self, synthetic):
        assert resolve_column(synthetic, ["nope", "feat_b"], "test") == "feat_b"

    def test_raises_with_available_columns_listed(self, synthetic):
        with pytest.raises(ColumnNotFound) as exc:
            resolve_column(synthetic, ["definitely_absent"], "test")
        assert "feat_a" in str(exc.value)


class TestFeatureContract:
    def test_feature_names_holds_no_forbidden_column(self):
        """Guards the other end of the pipe from Task 11: labels must
        not reach features inside the computer, AND must not be
        declared as features in the first place."""
        assert set(FEATURE_NAMES) & FORBIDDEN_AS_FEATURES == set()

    def test_feature_names_has_no_duplicates(self):
        assert len(FEATURE_NAMES) == len(set(FEATURE_NAMES))