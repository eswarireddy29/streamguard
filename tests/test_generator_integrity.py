"""
tests/test_generator_integrity.py

Task 13.7C - structural guards on the generated data.

WHY THIS FILE EXISTS. Every bug in this project so far has been
silent: nothing crashed, the numbers just looked plausible. The
timezone displacement, the doubled rows, the fraud anchored to the
wrong window, is_new_device = 1.0 on four patterns, CNP sharing one
timestamp. All five were found by a human noticing an odd number.

These tests turn that noticing into PASS/FAIL.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from streamguard.ml.splitter import split


@pytest.fixture(scope="module")
def blocks():
    try:
        b = split(save_manifest=False)
    except FileNotFoundError:
        pytest.skip("features.parquet not built")
    return b


@pytest.fixture(scope="module")
def train(blocks):
    return blocks["train"]


class TestNoLabelProxy:
    """A fraud pattern must SHIFT a feature, never pin it to a constant.

    A binary feature stuck at one value on every row of a pattern is
    the generator marking its own fraud - the is_new_device failure,
    which carried 58.65% of model gain before it was caught.
    """

    # Legitimate constants, with the reason each one is allowed:
    ALLOWED = {
        # EntryMode.MANUAL IS the definition of card-not-present.
        ("is_manual_entry", "card_not_present"),
        # These patterns have gaps of hours; zero short-window velocity
        # is arithmetically correct, not a leak.
        ("txn_count_1m", "geo_impossible"),
        ("txn_count_1m", "merchant_collusion"),
        ("txn_count_5m", "geo_impossible"),
        ("txn_count_5m", "merchant_collusion"),
        ("velocity_ratio_5m_24h", "geo_impossible"),
        ("velocity_ratio_5m_24h", "merchant_collusion"),
        # The six colluding merchants are a fixed offline set - a known
        # synthetic-data limitation recorded at Task 10.
        ("merchant_is_online", "merchant_collusion"),
        # Nearly all traffic is single-country; 1.0 vs 0.99 is not a proxy.
        ("distinct_countries_24h", "card_not_present"),
        ("distinct_countries_24h", "merchant_collusion"),
        ("distinct_countries_24h", "account_takeover"),
    }

    def test_no_binary_feature_is_pinned(self, train):
        if "fraud_type" not in train.meta.columns:
            pytest.skip("fraud_type not in metadata")

        X = train.X
        y = np.asarray(train.y).astype(bool)
        ft = train.meta["fraud_type"].reset_index(drop=True)

        offenders = []
        for col in X.columns:
            x = X[col].to_numpy(dtype=float)
            if not set(np.unique(x)).issubset({0.0, 1.0}):
                continue
            p_normal = float(x[~y].mean())
            for pat in sorted(ft[y].dropna().unique()):
                m = y & (ft == pat).to_numpy()
                if m.sum() < 30:
                    continue
                vals = np.unique(x[m])
                if len(vals) == 1 and abs(float(vals[0]) - p_normal) > 0.5:
                    if (col, str(pat)) not in self.ALLOWED:
                        offenders.append(
                            f"{col} = {vals[0]:.1f} on every {pat} row "
                            f"(normal {p_normal:.3f})"
                        )

        assert not offenders, (
            "label proxies found - the generator is marking its own fraud:\n  "
            + "\n  ".join(offenders)
        )


class TestTimestamps:
    """Two transactions on one card must not share an exact instant.

    A zero time gap divides into the implied-speed sentinel (99,999),
    which made 62.6% of card-not-present rows look like teleportation.

    A SMALL number of collisions is expected and harmless: normal
    traffic is generated from a Poisson process at one-second
    resolution, so two independent transactions on the same card
    occasionally land on the same second. What must never happen is a
    fraud EPISODE sharing one timestamp across its rows - that is a
    loop that forgot to advance its clock.
    """

    # Poisson collisions in normal traffic. 12 in 791k is noise.
    MAX_INCIDENTAL = 50

    def test_fraud_episodes_advance_their_clock(self, train):
        """ZERO tolerance for fraud rows sharing a timestamp."""
        meta = train.meta
        tcol = "_local_time"
        card_col = next((c for c in ("card_ref", "card_id") if c in meta.columns), None)
        if card_col is None or tcol not in meta.columns:
            pytest.skip("card or time column not in metadata")
        if "fraud_type" not in meta.columns:
            pytest.skip("fraud_type not in metadata")

        # NOTE: normal rows carry the STRING "none", not a null, so
        # .notna() would match all 791k rows. Filter on is_fraud.
        if "is_fraud" in meta.columns:
            fraud = meta[meta["is_fraud"].astype(bool)]
        else:
            fraud = meta[~meta["fraud_type"].isin(["none", None])
                         & meta["fraud_type"].notna()]

        dupes = int(fraud.duplicated(subset=[card_col, tcol]).sum())
        assert dupes == 0, (
            f"{dupes} FRAUD transactions share a card and an exact "
            "timestamp. A pattern's generation loop is not advancing t."
        )

    def test_incidental_collisions_stay_rare(self, train):
        """Normal-traffic collisions are tolerated but bounded."""
        meta = train.meta
        tcol = "_local_time"
        card_col = next((c for c in ("card_ref", "card_id") if c in meta.columns), None)
        if card_col is None or tcol not in meta.columns:
            pytest.skip("card or time column not in metadata")

        dupes = int(meta.duplicated(subset=[card_col, tcol]).sum())
        assert dupes <= self.MAX_INCIDENTAL, (
            f"{dupes} transactions share a card and an exact timestamp, "
            f"above the {self.MAX_INCIDENTAL} expected from Poisson "
            "collisions. Something is pinning timestamps."
        )

    def test_zero_gaps_stay_rare(self, train):
        if "seconds_since_prev" not in train.X.columns:
            pytest.skip("seconds_since_prev not a feature")
        s = train.X["seconds_since_prev"].to_numpy(dtype=float)
        # -1 is the documented first-transaction sentinel; 0 is not.
        zeros = int((s == 0).sum())
        assert zeros <= self.MAX_INCIDENTAL, (
            f"{zeros} rows have a zero-second gap from the previous "
            f"transaction on the same card, above the "
            f"{self.MAX_INCIDENTAL} expected from Poisson collisions."
        )

class TestGeographicRealism:
    """Fraud must not be separable by distance from home alone.

    Normal traffic uses distance decay (median 2.3 km, p99 21.7 km).
    Fraud using uniform merchant selection sat at a median of 925 km,
    making distance a marker worth 46.84% of model gain.
    """

    # geo_impossible is SUPPOSED to be far away - that is the pattern.
    EXEMPT = {"geo_impossible"}

    def test_fraud_distance_overlaps_normal(self, train):
        col = "distance_from_home_km"
        if col not in train.X.columns or "fraud_type" not in train.meta.columns:
            pytest.skip("column not available")

        x = train.X[col].to_numpy(dtype=float)
        y = np.asarray(train.y).astype(bool)
        ft = train.meta["fraud_type"].reset_index(drop=True)
        normal_p99 = float(np.percentile(x[~y], 99))

        offenders = []
        for pat in sorted(ft[y].dropna().unique()):
            if str(pat) in self.EXEMPT:
                continue
            m = y & (ft == pat).to_numpy()
            if m.sum() < 30:
                continue
            p10 = float(np.percentile(x[m], 10))
            if p10 > normal_p99:
                offenders.append(
                    f"{pat}: 10th percentile {p10:,.0f} km is above "
                    f"normal's 99th ({normal_p99:,.0f} km)"
                )

        assert not offenders, (
            "fraud is separable by distance alone:\n  " + "\n  ".join(offenders)
        )