"""
Checks on the built feature file.

These validate the OUTPUT rather than the logic: right number of
rows, no NaN, chronological order, labels intact.
"""

from __future__ import annotations

import duckdb
import pytest

from streamguard.features.computer import FEATURE_NAMES

pytestmark = pytest.mark.slow


@pytest.fixture
def con(feature_file):
    """DuckDB connection with the feature file registered as a view."""
    connection = duckdb.connect()
    connection.execute(
        f"CREATE VIEW f AS SELECT * FROM read_parquet('{feature_file.as_posix()}')"
    )
    return connection


class TestFeatureFileIntegrity:

    def test_all_features_present(self, con):
        columns = {row[1] for row in con.execute("PRAGMA table_info('f')").fetchall()}
        missing = [name for name in FEATURE_NAMES if name not in columns]
        assert not missing, f"missing columns: {missing}"

    def test_row_count_matches_database(self, con):
        """The feature file must cover every transaction, with none duplicated."""
        from streamguard.eventlog.txn_source import count_transactions

        rows = con.execute("SELECT COUNT(*) FROM f").fetchone()[0]
        assert rows == count_transactions()

    def test_transaction_refs_unique(self, con):
        """A duplicate would mean an event was processed twice."""
        total, distinct = con.execute(
            "SELECT COUNT(*), COUNT(DISTINCT transaction_ref) FROM f"
        ).fetchone()
        assert total == distinct

    def test_offsets_are_contiguous(self, con):
        """Offsets must run 0..N-1 with no gaps."""
        min_o, max_o, n = con.execute(
            "SELECT MIN(event_offset), MAX(event_offset), COUNT(*) FROM f"
        ).fetchone()
        assert min_o == 0
        assert max_o == n - 1

    def test_chronological_order(self, con):
        """
        Rows must be ordered by time.

        Out-of-order rows would mean the features were computed
        against scrambled history.
        """
        violations = con.execute("""
            SELECT COUNT(*) FROM (
                SELECT occurred_at,
                       LAG(occurred_at) OVER (ORDER BY event_offset) AS prev
                FROM f
            ) WHERE prev IS NOT NULL AND occurred_at < prev
        """).fetchone()[0]
        assert violations == 0

    def test_no_nan_or_infinity(self, con):
        """Every numeric feature column must be finite."""
        bad = []
        for name in FEATURE_NAMES:
            count = con.execute(
                f"SELECT COUNT(*) FROM f WHERE isnan({name}) OR isinf({name})"
            ).fetchone()[0]
            if count:
                bad.append((name, count))
        assert not bad, f"NaN or infinity found: {bad}"

    def test_fraud_rate_is_plausible(self, con):
        """
        The fraud rate should sit near the configured value.

        A wild deviation means injection or loading went wrong.
        """
        from streamguard.config.settings import settings

        total, fraud = con.execute(
            "SELECT COUNT(*), SUM(CASE WHEN is_fraud THEN 1 ELSE 0 END) FROM f"
        ).fetchone()
        rate = fraud / total

        assert 0.5 * settings.fraud_rate < rate < 2.0 * settings.fraud_rate, (
            f"fraud rate {rate:.4%} is far from configured "
            f"{settings.fraud_rate:.4%}"
        )

    def test_all_fraud_types_present(self, con):
        """All five patterns must appear, or injection missed one."""
        found = {
            row[0] for row in
            con.execute(
                "SELECT DISTINCT fraud_type FROM f WHERE is_fraud"
            ).fetchall()
        }
        expected = {"card_testing", "account_takeover", "geo_impossible",
                    "merchant_collusion", "card_not_present"}
        assert expected.issubset(found), f"missing: {expected - found}"

    def test_amounts_are_positive(self, con):
        count = con.execute("SELECT COUNT(*) FROM f WHERE amount <= 0").fetchone()[0]
        assert count == 0