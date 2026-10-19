"""Quick check that handler error isolation works."""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from streamguard.eventlog.event import Event, EventType  # noqa: E402
from streamguard.eventlog.handlers import (  # noqa: E402
    CountingHandler,
    EventHandler,
    OrderCheckHandler,
)


class BoomHandler(EventHandler):
    """A handler that always fails, to prove failures are contained."""

    def handle(self, event: Event) -> None:
        raise ValueError("deliberate failure")


def main() -> None:
    now = datetime.now(timezone.utc)
    event = Event(EventType.TRANSACTION.value, now, "CARD1", {"n": 1}, offset=0)

    print("\n--- Normal handlers ---")
    counter = CountingHandler()
    order = OrderCheckHandler()
    counter._handle_timed(event)
    order._handle_timed(event)
    print(f"counted      : {counter.by_type}")
    print(f"unique keys  : {len(counter.unique_keys)}")
    print(f"processed    : {counter.stats.processed}")
    print(f"errors       : {counter.stats.errors}")
    print(f"avg time     : {counter.stats.avg_ms:.4f} ms")

    print("\n--- Failing handler ---")
    boom = BoomHandler()
    returned = boom._handle_timed(event)
    print(f"returned     : {returned}")
    print(f"errors       : {boom.stats.errors}")
    print(f"last error   : {boom.stats.last_error}")
    print(f"error rate   : {boom.stats.error_rate}")

    print("\nThe exception was caught, counted and recorded.")
    print("Execution continued — that is what the processor relies on.\n")


if __name__ == "__main__":
    main()