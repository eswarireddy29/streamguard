"""
Check that features actually separate fraud from normal.

If they do not, no model will either, and Phase D is pointless.
Better to know now.
"""

import sys
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from streamguard.config.settings import settings  # noqa: E402

PATH = settings.processed_data_path / "features.parquet"

# Features where fraud should differ most, by pattern
PROBES = [
    ("card_testing", ["txn_count_5m", "velocity_ratio_5m_24h",
                      "amount_ratio_card_mean", "distinct_merchants_1h"]),
    ("account_takeover", ["amount_ratio_card_mean", "is_new_merchant",
                          "is_new_device", "amount_zscore_card"]),
    ("geo_impossible", ["implied_speed_kmh", "is_speed_implausible",
                        "distance_from_prev_km", "is_foreign_country"]),
    ("merchant_collusion", ["merchant_amount_zscore",
                            "amount_vs_merchant_mean", "merchant_txn_count"]),
    ("card_not_present", ["is_manual_entry", "is_ecommerce",
                          "amount_ratio_card_mean", "is_card_present"]),
]


def main() -> None:
    if not PATH.exists():
        print(f"\n  Not found: {PATH}")
        print("  Run: python scripts/build_features.py\n")
        sys.exit(1)

    con = duckdb.connect()
    rel = f"read_parquet('{PATH.as_posix()}')"

    print("\n" + "=" * 70)
    print("  FEATURE SEPARATION CHECK")
    print("=" * 70)

    total, fraud = con.execute(
        f"SELECT COUNT(*), SUM(CASE WHEN is_fraud THEN 1 ELSE 0 END) FROM {rel}"
    ).fetchone()
    print(f"\n  Rows: {total:,}   Fraud: {fraud:,} "
          f"({100.0 * fraud / total:.3f}%)\n")

    # Data quality
    print("  --- Data quality ---")
    nan_cols = []
    cols = con.execute(f"SELECT * FROM {rel} LIMIT 0").description
    numeric = [c[0] for c in cols if c[0] not in (
        "transaction_ref", "occurred_at", "card_ref", "customer_ref",
        "merchant_ref", "fraud_type", "is_fraud", "event_offset")]

    for col in numeric:
        bad = con.execute(
            f"SELECT COUNT(*) FROM {rel} WHERE isnan({col}) OR isinf({col})"
        ).fetchone()[0]
        if bad:
            nan_cols.append((col, bad))

    print(f"  NaN/inf columns : {nan_cols or 'none'}")

    # Per-pattern separation
    for pattern, features in PROBES:
        n = con.execute(
            f"SELECT COUNT(*) FROM {rel} WHERE fraud_type = '{pattern}'"
        ).fetchone()[0]

        print(f"\n  --- {pattern}  (n={n:,}) ---")
        print(f"  {'feature':<26} {'normal':>14} {'fraud':>14} {'ratio':>9}")

        for feat in features:
            row = con.execute(f"""
                SELECT
                  AVG(CASE WHEN NOT is_fraud THEN {feat} END),
                  AVG(CASE WHEN fraud_type = '{pattern}' THEN {feat} END)
                FROM {rel}
            """).fetchone()

            normal, frauds = row[0] or 0.0, row[1] or 0.0
            ratio = frauds / normal if abs(normal) > 1e-9 else float("inf")
            flag = " <<<" if (ratio > 2 or ratio < 0.5) else ""
            print(f"  {feat:<26} {normal:>14,.3f} {frauds:>14,.3f} "
                  f"{ratio:>8.2f}x{flag}")

    print("\n" + "=" * 70)
    print("  '<<<' marks features where fraud differs from normal by 2x or")
    print("  more. Each pattern should have at least one.")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()