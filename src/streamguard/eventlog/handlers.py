"""
Event handlers.

A handler is one unit of work applied to each event. The processor
runs registered handlers in order, so each stays a single concern:
the feature engine computes features, the scorer scores, the case
creator creates cases. None of them knows about the others.

Handlers must be IDEMPOTENT. Delivery is at-least-once, so the same
event can arrive twice after a crash, and processing it twice must
produce the same result as processing it once.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from streamguard.eventlog.event import Event
from streamguard.utils.logging_config import get_logger

log = get_logger(__name__)


@dataclass
class HandlerStats:
    """Per-handler counters, for the metrics report."""
    name: str
    processed: int = 0
    errors: int = 0
    total_seconds: float = 0.0
    last_error: str | None = None

    @property
    def avg_ms(self) -> float:
        if self.processed == 0:
            return 0.0
        return (self.total_seconds / self.processed) * 1000.0

    @property
    def error_rate(self) -> float:
        total = self.processed + self.errors
        return self.errors / total if total else 0.0


class EventHandler(ABC):
    """
    Base class for anything that processes events.

    Subclasses implement handle(). The optional lifecycle hooks
    on_start and on_stop exist for setup and teardown -- opening a
    database connection, flushing a buffer at the end.
    """

    def __init__(self, name: str | None = None):
        self.name = name or self.__class__.__name__
        self.stats = HandlerStats(name=self.name)

    @abstractmethod
    def handle(self, event: Event) -> None:
        """
        Process one event.

        Raising is allowed. The processor catches, counts and
        continues -- see the error policy in processor.py.
        """

    def on_start(self) -> None:
        """Called once before the first event."""

    def on_stop(self) -> None:
        """
        Called once after the last event, including after an error.

        This is where buffered work gets flushed. A handler that
        batches writes MUST flush here or it silently loses the
        final partial batch.
        """

    # ---------- Internal ----------

    def _handle_timed(self, event: Event) -> bool:
        """
        Run handle() with timing and error capture.

        Returns True on success, False if the handler raised.
        Used by the processor; not intended to be overridden.
        """
        started = time.perf_counter()
        try:
            self.handle(event)
            self.stats.processed += 1
            return True
        except Exception as exc:
            self.stats.errors += 1
            self.stats.last_error = f"{type(exc).__name__}: {exc}"
            log.warning(
                "handler_error",
                handler=self.name,
                offset=event.offset,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return False
        finally:
            self.stats.total_seconds += time.perf_counter() - started


# ============================================================
#  Built-in handlers
# ============================================================

class CountingHandler(EventHandler):
    """
    Counts events by type and key. Useful for smoke-testing the
    processor before real handlers exist.
    """

    def __init__(self, name: str = "counter"):
        super().__init__(name)
        self.by_type: dict[str, int] = {}
        self.unique_keys: set[str] = set()
        self.first_offset: int | None = None
        self.last_offset: int | None = None

    def handle(self, event: Event) -> None:
        self.by_type[event.event_type] = self.by_type.get(event.event_type, 0) + 1
        self.unique_keys.add(event.key)

        if self.first_offset is None:
            self.first_offset = event.offset
        self.last_offset = event.offset


class OrderCheckHandler(EventHandler):
    """
    Asserts that events arrive in chronological order.

    Worth running permanently in development: out-of-order events
    silently corrupt every rolling-window feature, and nothing else
    would tell you.
    """

    def __init__(self, name: str = "order_check"):
        super().__init__(name)
        self.previous_time = None
        self.violations = 0

    def handle(self, event: Event) -> None:
        if self.previous_time is not None and event.occurred_at < self.previous_time:
            self.violations += 1
            log.error(
                "out_of_order_event",
                offset=event.offset,
                occurred_at=event.occurred_at.isoformat(),
                previous=self.previous_time.isoformat(),
            )
        self.previous_time = event.occurred_at


class SamplingHandler(EventHandler):
    """
    Keeps every Nth event, for inspection during development.

    Holding all 791,112 events would exhaust memory; a sample of a
    few hundred is enough to eyeball what is flowing through.
    """

    def __init__(self, every: int = 10_000, max_kept: int = 200,
                 name: str = "sampler"):
        super().__init__(name)
        self.every = every
        self.max_kept = max_kept
        self.samples: list[Event] = []
        self._seen = 0

    def handle(self, event: Event) -> None:
        self._seen += 1
        if self._seen % self.every == 0 and len(self.samples) < self.max_kept:
            self.samples.append(event)