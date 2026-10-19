"""
Run the stream processor over the event log.

    python scripts/run_processor.py
    python scripts/run_processor.py --max-events 50000
    python scripts/run_processor.py --group myrun --from-beginning
"""

import sys
from pathlib import Path

import typer

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from streamguard.config.settings import settings  # noqa: E402
from streamguard.eventlog.consumer import FileEventConsumer  # noqa: E402
from streamguard.eventlog.handlers import (  # noqa: E402
    CountingHandler,
    OrderCheckHandler,
    SamplingHandler,
)
from streamguard.eventlog.processor import (  # noqa: E402
    ProcessorConfig,
    StreamProcessor,
)
from streamguard.utils.logging_config import get_logger, setup_logging  # noqa: E402

app = typer.Typer(add_completion=False)


@app.command()
def main(
    topic: str = typer.Option("transactions", help="Log topic"),
    group: str = typer.Option("processor", help="Consumer group"),
    from_beginning: bool = typer.Option(True, help="Start at offset 0"),
    max_events: int = typer.Option(None, help="Stop after N events"),
    batch_size: int = typer.Option(1000, help="Events per poll"),
) -> None:
    setup_logging()
    log = get_logger(__name__)

    print("\n" + "=" * 62)
    print("  STREAMGUARD — STREAM PROCESSOR")
    print("=" * 62)
    print(f"\n  Topic  : {topic}")
    print(f"  Group  : {group}")
    print(f"  Limit  : {max_events or 'none'}\n")

    consumer = FileEventConsumer(
        settings.event_log_path, topic, group, from_beginning=from_beginning
    )

    config = ProcessorConfig(batch_size=batch_size)

    processor = (
        StreamProcessor(consumer, config=config)
        .register(CountingHandler())
        .register(OrderCheckHandler())
        .register(SamplingHandler(every=100_000, max_kept=10))
    )

    print(f"  {'processed':>9} {'progress':>8} {'rate':>10} "
          f"{'lag':>12} {'errors':>9} {'eta':>8}")
    print("  " + "-" * 60)

    processor.run(max_events=max_events)
    processor.print_report()

    # Handler-specific findings
    counter = processor.handlers[0]
    order = processor.handlers[1]
    sampler = processor.handlers[2]

    print("  --- Findings ---")
    print(f"  Event types     : {counter.by_type}")
    print(f"  Unique cards    : {len(counter.unique_keys):,}")
    print(f"  Offset range    : {counter.first_offset:,} .. "
          f"{counter.last_offset:,}")
    print(f"  Order violations: {order.violations:,}")

    if sampler.samples:
        e = sampler.samples[0]
        print(f"\n  Sample event @ offset {e.offset:,}")
        print(f"    time     : {e.occurred_at.isoformat()}")
        print(f"    card     : {e.key}")
        print(f"    amount   : Rs {e.payload.get('amount'):,.2f}")
        print(f"    merchant : {e.payload.get('merchant_category')}")
        print(f"    channel  : {e.payload.get('channel')}")

    print()
    log.info("processor_run_complete", **processor.metrics.summary())


if __name__ == "__main__":
    app()