"""Verify running statistics and card state behave correctly."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402

from streamguard.features.state import CardState, TransactionMemory  # noqa: E402
from streamguard.features.stats import RunningStats  # noqa: E402

IST = timezone(timedelta(hours=5, minutes=30))


def test_welford_matches_numpy() -> None:
    print("\n--- Welford vs numpy ---")
    rng = np.random.default_rng(42)
    values = rng.lognormal(mean=np.log(5000), sigma=1.2, size=10_000)

    stats = RunningStats()
    for v in values:
        stats.update(float(v))

    print(f"  count    : welford {stats.count:>12,}  numpy {len(values):>12,}")
    print(f"  mean     : welford {stats.mean:>12.6f}  numpy {values.mean():>12.6f}")
    print(f"  std      : welford {stats.std:>12.6f}  numpy {values.std(ddof=1):>12.6f}")

    mean_ok = abs(stats.mean - values.mean()) < 1e-6
    std_ok = abs(stats.std - values.std(ddof=1)) < 1e-6
    print(f"  match    : {'OK' if mean_ok and std_ok else 'FAIL'}")


def test_z_score_guards() -> None:
    print("\n--- z-score edge cases ---")
    empty = RunningStats()
    print(f"  no history      : {empty.z_score(5000.0)}  (expect 0.0)")

    one = RunningStats()
    one.update(1000.0)
    print(f"  one observation : {one.z_score(5000.0)}  (expect 0.0)")

    flat = RunningStats()
    for _ in range(10):
        flat.update(500.0)
    print(f"  zero variance   : {flat.z_score(5000.0)}  (expect 0.0)")

    normal = RunningStats()
    for v in [100, 120, 90, 110, 105, 95]:
        normal.update(float(v))
    print(f"  typical value   : {normal.z_score(105.0):.3f}  (expect near 0)")
    print(f"  extreme value   : {normal.z_score(5000.0):.1f}  (expect large)")


def test_windows() -> None:
    print("\n--- Time windows ---")
    base = datetime(2026, 3, 1, 12, 0, 0, tzinfo=IST)
    state = CardState("CARD0000001")

    # Six transactions: 0, 30s, 2m, 10m, 90m and 300m ago
    for minutes in [300, 90, 10, 2, 0.5, 0]:
        when = base - timedelta(minutes=minutes)
        state.update(
            TransactionMemory(when, 500.0, 19.07, 72.87,
                              "MERCH000001", "5411", "Mumbai", "pos"),
            device_ref="DEV0000001", country="IN",
        )

    now = base + timedelta(seconds=1)
    for label, window in [
        ("1 minute ", timedelta(minutes=1)),
        ("5 minutes", timedelta(minutes=5)),
        ("1 hour   ", timedelta(hours=1)),
        ("24 hours ", timedelta(hours=24)),
    ]:
        print(f"  {label}: {state.count_within(now, window)}")

    print(f"  total kept : {len(state.recent)}")
    print(f"  (expect 1m=2, 5m=3, 1h=4, 24h=6)")


def test_deque_bound() -> None:
    print("\n--- Memory bound ---")
    base = datetime(2026, 3, 1, tzinfo=IST)
    state = CardState("CARD0000002")

    for i in range(500):
        state.update(
            TransactionMemory(base + timedelta(minutes=i), 100.0, 0.0, 0.0,
                              f"MERCH{i:06d}", "5411", "Mumbai", "pos"),
            device_ref=None, country="IN",
        )

    print(f"  fed 500 transactions")
    print(f"  deque length     : {len(state.recent)}  (expect 50)")
    print(f"  total_count      : {state.total_count}  (expect 500)")
    print(f"  amount_stats n   : {state.amount_stats.count}  (expect 500)")
    print(f"  seen_merchants   : {len(state.seen_merchants)}  (expect 200, capped)")
    print("\n  Deque bounded, but full-history aggregates still complete.")


if __name__ == "__main__":
    test_welford_matches_numpy()
    test_z_score_guards()
    test_windows()
    test_deque_bound()
    print()