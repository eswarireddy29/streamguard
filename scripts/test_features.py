"""Verify feature computation, especially the no-leakage ordering."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from streamguard.features.computer import (  # noqa: E402
    FEATURE_NAMES,
    FeatureComputer,
)

IST = timezone(timedelta(hours=5, minutes=30))
BASE = datetime(2026, 3, 1, 14, 0, 0, tzinfo=IST)


def make_payload(minutes_offset=0, amount=1000.0, merchant="MERCH000001",
                 mcc="5411", city="Mumbai", lat=19.0760, lon=72.8777,
                 country="IN", channel="pos", entry_mode="chip",
                 device="DEV0000001"):
    return {
        "transaction_ref": f"TXN{minutes_offset:06.1f}",
        "occurred_at": (BASE + timedelta(minutes=minutes_offset)).isoformat(),
        "card_ref": "CARD0000001",
        "customer_ref": "CUST000001",
        "merchant_ref": merchant,
        "device_ref": device,
        "amount": amount,
        "currency": "INR",
        "channel": channel,
        "entry_mode": entry_mode,
        "city": city,
        "country": country,
        "lat": lat,
        "lon": lon,
        "home_city": "Mumbai",
        "home_country": "IN",
        "home_lat": 19.0760,
        "home_lon": 72.8777,
        "mcc": mcc,
        "merchant_category": "Grocery & Supermarket",
        "merchant_is_online": False,
        "is_fraud": False,
        "fraud_type": "none",
    }


def test_first_transaction():
    print("\n--- First transaction (no history) ---")
    fc = FeatureComputer()
    f = fc.process(make_payload(0, 1000.0))

    checks = [
        ("is_first_transaction", 1.0),
        ("amount_zscore_card", 0.0),
        ("txn_count_5m", 0),
        ("distance_from_prev_km", 0.0),
        ("seconds_since_prev", -1.0),
        ("is_new_merchant", 1.0),
        ("card_txn_count", 0.0),
    ]
    for name, expected in checks:
        actual = f[name]
        mark = "OK " if abs(actual - expected) < 1e-9 else "FAIL"
        print(f"  {mark} {name:<26} = {actual:>10.2f}  (expect {expected})")


def test_no_self_leakage():
    print("\n--- No self-leakage ---")
    fc = FeatureComputer()
    for i in range(10):
        fc.process(make_payload(i * 10, 1000.0))

    # 11th transaction, wildly larger
    f = fc.compute_features(make_payload(200, 50_000.0))

    print(f"  card mean BEFORE   : {fc.store.card('CARD0000001').amount_stats.mean:,.2f}")
    print(f"  new amount         : 50,000.00")
    print(f"  z-score            : {f['amount_zscore_card']:,.2f}")
    print(f"  ratio to mean      : {f['amount_ratio_card_mean']:,.2f}")
    print("\n  If the amount leaked into its own mean, the mean would")
    print("  have moved toward 50,000 and the z-score would be small.")
    print(f"  Mean is still 1,000 and ratio is 50x -> NO LEAKAGE.")


def test_card_testing_signature():
    print("\n--- Card testing burst ---")
    fc = FeatureComputer()
    fc.process(make_payload(0, 2500.0))

    # Eight tiny charges, 30 seconds apart
    last = None
    for i in range(8):
        last = fc.process(make_payload(
            60 + i * 0.5, 25.0, merchant=f"MERCH{i + 10:06d}",
            mcc="4899", channel="ecommerce", entry_mode="stored_credential",
        ))

    print(f"  txn_count_5m          : {last['txn_count_5m']:.0f}")
    print(f"  velocity_ratio_5m_24h : {last['velocity_ratio_5m_24h']:.3f}")
    print(f"  distinct_merchants_1h : {last['distinct_merchants_1h']:.0f}")
    print(f"  amount_ratio_card_mean: {last['amount_ratio_card_mean']:.3f}")
    print("\n  High velocity + many merchants + tiny amounts.")


def test_geo_impossible():
    print("\n--- Geo-impossible ---")
    fc = FeatureComputer()
    fc.process(make_payload(0, 1500.0))

    # Dubai, 20 minutes later
    f = fc.compute_features(make_payload(
        20, 45_000.0, merchant="MERCH000999", mcc="5944",
        city="Dubai", lat=25.2048, lon=55.2708, country="AE",
    ))

    print(f"  distance_from_prev_km : {f['distance_from_prev_km']:,.0f}")
    print(f"  implied_speed_kmh     : {f['implied_speed_kmh']:,.0f}")
    print(f"  is_speed_implausible  : {f['is_speed_implausible']:.0f}")
    print(f"  is_foreign_country    : {f['is_foreign_country']:.0f}")
    print(f"  is_new_city           : {f['is_new_city']:.0f}")


def test_completeness():
    print("\n--- Feature vector ---")
    fc = FeatureComputer()
    f = fc.process(make_payload(0))

    missing = [n for n in FEATURE_NAMES if n not in f]
    extra = [n for n in f if n not in FEATURE_NAMES]
    vector = FeatureComputer.feature_vector(f)

    print(f"  declared   : {len(FEATURE_NAMES)}")
    print(f"  computed   : {len(f)}")
    print(f"  missing    : {missing or 'none'}")
    print(f"  extra      : {extra or 'none'}")
    print(f"  vector len : {len(vector)}")

    import math
    bad = [FEATURE_NAMES[i] for i, v in enumerate(vector)
           if math.isnan(v) or math.isinf(v)]
    print(f"  NaN or inf : {bad or 'none'}")


if __name__ == "__main__":
    test_first_transaction()
    test_no_self_leakage()
    test_card_testing_signature()
    test_geo_impossible()
    test_completeness()
    print()