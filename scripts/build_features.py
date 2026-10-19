"""
Compute features for every event in the log and write them to Parquet.

    python scripts/build_features.py
    python scripts/build_features.py --max-events 50000
"""

import sys
from pathlib import Path

import typer

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from streamguard.config.settings import settings  # noqa: E402
from streamguard.eventlog.consumer import FileEventConsumer  # noqa: E402
from streamguard.eventlog.processor import (  # noqa: E402
    ProcessorConfig,
    StreamProcessor,
)
from streamguard.features.computer import FEATURE_NAMES  # noqa: E402
from streamguard.features.handler import FeatureHandler  # noqa: E402
from streamguard.features.state import RECENT_WINDOW  # noqa: E402
from streamguard.utils.logging_config import get_logger, setup_logging  # noqa: E402

app = typer.Typer(add_completion=False)


@app.command()
def main(
    topic: str = typer.Option("transactions", help="Log topic"),
    output: str = typer.Option("features.parquet", help="Output filename"),
    max_events: int = typer.Option(None, help="Stop after N events"),
    batch_size: int = typer.Option(2000, help="Events per poll"),
) -> None:
    setup_logging()
    log = get_logger(__name__)

    out_path = settings.processed_data_path / output

    print("\n" + "=" * 62)
    print("  STREAMGUARD — FEATURE BUILD")
    print("=" * 62)
    print(f"\n  Topic    : {topic}")
    print(f"  Features : {len(FEATURE_NAMES)}")
    print(f"  Output   : {out_path}")
    print(f"  Limit    : {max_events or 'none'}\n")

    # from_beginning=True always: features must be computed over the
    # whole history in order, or the state would start mid-stream
    # with no past to draw on.
    consumer = FileEventConsumer(
        settings.event_log_path, topic, "feature_builder", from_beginning=True
    )

    handler = FeatureHandler(out_path)
    processor = StreamProcessor(
        consumer,
        config=ProcessorConfig(batch_size=batch_size, progress_every_n=50_000),
    ).register(handler)

    print(f"  {'processed':>9} {'progress':>8} {'rate':>10} "
          f"{'lag':>12} {'errors':>9} {'eta':>8}")
    print("  " + "-" * 60)

    processor.run(max_events=max_events)
    processor.print_report()

    print("  --- Feature build ---")
    print(f"  Rows written    : {handler.writer.rows_written:,}")
    print(f"  Chunks          : {handler.writer.chunks_written}")

    size_mb = out_path.stat().st_size / (1024 * 1024) if out_path.exists() else 0
    print(f"  File size       : {size_mb:,.1f} MB")

    summary = handler.store.summary()
    print(f"\n  Cards tracked   : {summary['cards']:,}")
    print(f"  Merchants       : {summary['merchants']:,}")
    print(f"  Customers       : {summary['customers']:,}")

    print(f"\n  Max deque used  : {handler.max_deque_len} / {RECENT_WINDOW}")
    print(f"  Max 24h count   : {handler.max_count_24h}")

    if handler.max_count_24h >= RECENT_WINDOW:
        print(f"\n  WARNING: a card reached {handler.max_count_24h} "
              f"transactions in 24h, at or above RECENT_WINDOW "
              f"({RECENT_WINDOW}).")
        print("  The 24h velocity window was silently truncated for that")
        print("  card. Raise RECENT_WINDOW and rebuild.")
    else:
        print(f"\n  OK: the deque ceiling was never a binding constraint.")

    print("=" * 62 + "\n")
    log.info("feature_build_complete", rows=handler.writer.rows_written)


if __name__ == "__main__":
    app()