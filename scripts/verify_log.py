"""Verify the event log is complete, ordered and leak-free."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from streamguard.config.settings import settings  # noqa: E402
from streamguard.eventlog.consumer import FileEventConsumer  # noqa: E402
from streamguard.eventlog.txn_source import count_transactions  # noqa: E402

TOPIC = "transactions"


def main() -> None:
    print("\n" + "=" * 62)
    print("  EVENT LOG VERIFICATION")
    print("=" * 62 + "\n")

    consumer = FileEventConsumer(
        settings.event_log_path, TOPIC, "verify", from_beginning=True
    )

    log_end = consumer.log_end_offset()
    db_count = count_transactions()
    print(f"  Log end offset   : {log_end:,}")
    print(f"  DB transactions  : {db_count:,}")
    print(f"  Completeness     : {'OK' if log_end == db_count else 'MISMATCH'}")

    print("\n  Scanning every event...")
    prev_time = None
    prev_offset = -1
    out_of_order = 0
    offset_gaps = 0
    fraud_count = 0
    checked = 0

    for event in consumer.stream(batch_size=10_000):
        checked += 1

        if prev_time is not None and event.occurred_at < prev_time:
            out_of_order += 1
        prev_time = event.occurred_at

        if event.offset != prev_offset + 1:
            offset_gaps += 1
        prev_offset = event.offset

        if event.payload.get("is_fraud"):
            fraud_count += 1

    print(f"  Events scanned   : {checked:,}")
    print(f"  Out of order     : {out_of_order:,}  "
          f"{'OK' if out_of_order == 0 else 'FAIL'}")
    print(f"  Offset gaps      : {offset_gaps:,}  "
          f"{'OK' if offset_gaps == 0 else 'FAIL'}")
    print(f"  Fraud events     : {fraud_count:,}  "
          f"({100.0 * fraud_count / max(checked, 1):.3f}%)")

    passed = (log_end == db_count and out_of_order == 0 and offset_gaps == 0)
    print("\n  " + ("ALL CHECKS PASSED" if passed else "CHECKS FAILED"))
    print("=" * 62 + "\n")

    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()