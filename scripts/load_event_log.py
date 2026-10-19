"""
Load all transactions from PostgreSQL into the event log.

    python scripts/load_event_log.py
    python scripts/load_event_log.py --topic transactions --truncate
    python scripts/load_event_log.py --limit 1000
"""

import sys
import time
from pathlib import Path

import typer

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from streamguard.config.settings import settings  # noqa: E402
from streamguard.eventlog.producer import FileEventProducer  # noqa: E402
from streamguard.eventlog.txn_source import (  # noqa: E402
    count_transactions,
    stream_transaction_events,
)
from streamguard.utils.logging_config import get_logger, setup_logging  # noqa: E402

app = typer.Typer(add_completion=False)

BATCH_SIZE = 5_000


@app.command()
def main(
    topic: str = typer.Option("transactions", help="Log topic name"),
    truncate: bool = typer.Option(True, help="Clear the log first"),
    limit: int = typer.Option(None, help="Stop after N events (for testing)"),
) -> None:
    setup_logging()
    log = get_logger(__name__)

    print("\n" + "=" * 62)
    print("  STREAMGUARD — EVENT LOG LOAD")
    print("=" * 62)

    total_available = count_transactions()
    target = min(limit, total_available) if limit else total_available

    print(f"\n  Topic      : {topic}")
    print(f"  Truncate   : {truncate}")
    print(f"  In database: {total_available:,}")
    print(f"  To load    : {target:,}")
    print(f"  Destination: {settings.event_log_path / topic}\n")

    started = time.perf_counter()
    written = 0
    batch = []

    with FileEventProducer(
        settings.event_log_path, topic=topic, truncate=truncate
    ) as producer:

        for event in stream_transaction_events():
            batch.append(event)

            if len(batch) >= BATCH_SIZE:
                written += producer.append_many(batch)
                batch.clear()

                if written % 100_000 == 0:
                    elapsed = time.perf_counter() - started
                    rate = written / elapsed if elapsed else 0
                    pct = 100.0 * written / target
                    print(f"  {written:>9,} / {target:,}  "
                          f"({pct:5.1f}%)  {rate:>8,.0f}/s")

            if limit and written + len(batch) >= limit:
                break

        if batch:
            written += producer.append_many(batch)

        producer.flush()
        final_offset = producer.next_offset

    elapsed = time.perf_counter() - started

    print("\n  --- Complete ---")
    print(f"  Events written : {written:,}")
    print(f"  Next offset    : {final_offset:,}")
    print(f"  Time           : {elapsed:.1f}s")
    print(f"  Rate           : {written / max(elapsed, 0.001):,.0f}/s")

    log_dir = settings.event_log_path / topic
    segments = sorted(log_dir.glob("*.jsonl"))
    size_mb = sum(s.stat().st_size for s in segments) / (1024 * 1024)
    print(f"  Segments       : {len(segments)}")
    print(f"  Disk used      : {size_mb:,.1f} MB")
    print("=" * 62 + "\n")

    log.info("event_log_loaded", events=written, segments=len(segments),
             size_mb=round(size_mb, 1), seconds=round(elapsed, 1))


if __name__ == "__main__":
    app()