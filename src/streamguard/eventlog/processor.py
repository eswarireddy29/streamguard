"""
Stream processor.

Polls the event log, runs each event through a chain of handlers,
commits offsets periodically, and reports health. This is the loop a
production streaming service runs.

Error policy: a handler that raises is logged and counted, and
processing continues. If the error RATE crosses a threshold, the
processor stops -- a few bad events are noise, a thousand are a
symptom, and continuing past that point does more harm than good.
"""

from __future__ import annotations

import signal
import time
from dataclasses import dataclass

from streamguard.eventlog.consumer import EventConsumer
from streamguard.eventlog.event import Event
from streamguard.eventlog.handlers import EventHandler
from streamguard.eventlog.metrics import ProcessorMetrics
from streamguard.utils.logging_config import get_logger

log = get_logger(__name__)


@dataclass
class ProcessorConfig:
    """
    Tuning for one processor run.

    checkpoint_every_n / checkpoint_every_seconds:
        Commit on whichever arrives first. The count bound keeps
        reprocessing after a crash bounded; the TIME bound matters
        because a slow stream should not sit un-checkpointed for an
        hour just because it has not hit N events yet.

    max_error_rate:
        Stop if this fraction of events fail, once we have seen
        enough events to judge. 0.01 = one percent.

    error_rate_grace:
        Do not apply the error-rate check until this many events
        have been seen. Without it, one failure in the first two
        events is a 50% error rate and would stop the run.
    """

    batch_size: int = 1_000
    checkpoint_every_n: int = 10_000
    checkpoint_every_seconds: float = 30.0
    max_error_rate: float = 0.01
    error_rate_grace: int = 1_000
    progress_every_n: int = 50_000
    stop_at_end: bool = True          # False = keep polling for new events
    poll_idle_seconds: float = 0.5    # wait when the log is drained


class StreamProcessor:
    """Runs handlers over events from a consumer."""

    def __init__(
        self,
        consumer: EventConsumer,
        handlers: list[EventHandler] | None = None,
        config: ProcessorConfig | None = None,
    ):
        self.consumer = consumer
        self.handlers: list[EventHandler] = handlers or []
        self.config = config or ProcessorConfig()
        self.metrics = ProcessorMetrics()

        self._running = False
        self._stop_requested = False
        self._since_checkpoint = 0
        self._last_checkpoint_time = time.perf_counter()

    # ---------- Registration ----------

    def register(self, handler: EventHandler) -> StreamProcessor:
        """
        Add a handler. Returns self so calls can be chained:

            processor.register(features).register(scorer)
        """
        self.handlers.append(handler)
        log.info("handler_registered", handler=handler.name,
                 position=len(self.handlers))
        return self

    # ---------- Lifecycle ----------

    def _install_signal_handlers(self) -> None:
        """
        Stop cleanly on Ctrl+C.

        Without this, Ctrl+C kills the process mid-batch: handlers
        never flush and the offset is never committed. With it, the
        current batch finishes, handlers flush, the offset commits,
        and the next run resumes exactly where this one stopped.
        """
        def _request_stop(signum, frame):
            if self._stop_requested:
                log.warning("force_quit")
                raise KeyboardInterrupt
            self._stop_requested = True
            log.warning("stop_requested_finishing_batch")

        try:
            signal.signal(signal.SIGINT, _request_stop)
        except (ValueError, OSError):
            # Signals only work on the main thread; ignore elsewhere
            pass

    def _start_handlers(self) -> None:
        for handler in self.handlers:
            handler.on_start()

    def _stop_handlers(self) -> None:
        """
        Called from a finally block, so it runs even after a crash.

        Handlers that buffer MUST flush here or the final partial
        batch is silently lost.
        """
        for handler in self.handlers:
            try:
                handler.on_stop()
            except Exception as exc:
                log.error("handler_stop_failed",
                          handler=handler.name, error=str(exc))

    # ---------- Processing ----------

    def _process_event(self, event: Event) -> bool:
        """
        Run one event through every handler.

        Returns True if all succeeded. A failure in one handler does
        not prevent the rest from running -- isolation is the point.
        """
        all_ok = True
        for handler in self.handlers:
            if not handler._handle_timed(event):
                all_ok = False
        return all_ok

    def _should_checkpoint(self) -> bool:
        if self._since_checkpoint >= self.config.checkpoint_every_n:
            return True
        elapsed = time.perf_counter() - self._last_checkpoint_time
        return elapsed >= self.config.checkpoint_every_seconds

    def _checkpoint(self) -> None:
        self.consumer.commit()
        self.metrics.commits += 1
        self.metrics.current_offset = self.consumer.position
        self._since_checkpoint = 0
        self._last_checkpoint_time = time.perf_counter()

    def _error_budget_exceeded(self) -> bool:
        seen = self.metrics.events_processed + self.metrics.events_failed
        if seen < self.config.error_rate_grace:
            return False
        return self.metrics.error_rate > self.config.max_error_rate

    def _report_progress(self) -> None:
        self.metrics.sample_rate()
        eta = self.metrics.eta_seconds()
        eta_text = f"{eta:,.0f}s" if eta is not None else "-"

        print(
            f"  {self.metrics.events_processed:>9,} "
            f"({self.metrics.progress_pct:5.1f}%)  "
            f"{self.metrics.recent_rate:>8,.0f}/s  "
            f"lag {self.metrics.lag:>8,}  "
            f"err {self.metrics.events_failed:>5,}  "
            f"eta {eta_text}"
        )

    # ---------- The loop ----------

    def run(self, max_events: int | None = None) -> ProcessorMetrics:
        """
        Process events until the log is drained, max_events is
        reached, or a stop is requested.

        Returns the metrics for the run.
        """
        self._install_signal_handlers()
        self._running = True
        self.metrics = ProcessorMetrics()
        self.metrics.current_offset = self.consumer.position
        self.metrics.log_end_offset = self.consumer.log_end_offset()

        log.info(
            "processor_started",
            handlers=[h.name for h in self.handlers],
            start_offset=self.metrics.current_offset,
            log_end=self.metrics.log_end_offset,
            batch_size=self.config.batch_size,
        )

        try:
            while self._running:
                if self._stop_requested:
                    log.info("stopping_as_requested")
                    break

                remaining = None
                if max_events is not None:
                    remaining = max_events - self.metrics.events_processed
                    if remaining <= 0:
                        break

                size = self.config.batch_size
                if remaining is not None:
                    size = min(size, remaining)

                batch = self.consumer.poll(size)

                if not batch:
                    # Log drained. Refresh the end offset in case the
                    # producer wrote more while we were working.
                    self.metrics.log_end_offset = self.consumer.log_end_offset()
                    if self.config.stop_at_end:
                        break
                    time.sleep(self.config.poll_idle_seconds)
                    continue

                self.metrics.batches += 1

                for event in batch:
                    if self._process_event(event):
                        self.metrics.events_processed += 1
                    else:
                        self.metrics.events_failed += 1

                    self._since_checkpoint += 1

                    total = (self.metrics.events_processed
                             + self.metrics.events_failed)
                    if total % self.config.progress_every_n == 0:
                        self.metrics.current_offset = (
                            self.consumer.position + self._since_checkpoint
                        )
                        self._report_progress()

                if self._should_checkpoint():
                    self._checkpoint()

                if self._error_budget_exceeded():
                    log.error(
                        "error_budget_exceeded_stopping",
                        error_rate=round(self.metrics.error_rate, 4),
                        limit=self.config.max_error_rate,
                        failed=self.metrics.events_failed,
                    )
                    break

        finally:
            # Always commit and always flush, even after an exception.
            # Losing a handler's buffered work because of a crash
            # elsewhere would be a silent data loss bug.
            self._checkpoint()
            self._stop_handlers()
            self._running = False
            self.metrics.log_end_offset = self.consumer.log_end_offset()

        log.info("processor_finished", **self.metrics.summary())
        return self.metrics

    def stop(self) -> None:
        """Request a clean stop from another thread."""
        self._stop_requested = True

    # ---------- Reporting ----------

    def print_report(self) -> None:
        m = self.metrics

        print("\n" + "=" * 62)
        print("  PROCESSOR REPORT")
        print("=" * 62)
        print(f"\n  Processed    : {m.events_processed:,}")
        print(f"  Failed       : {m.events_failed:,}  "
              f"({m.error_rate:.4%})")
        print(f"  Batches      : {m.batches:,}")
        print(f"  Commits      : {m.commits:,}")
        print(f"  Elapsed      : {m.elapsed:.1f}s")
        print(f"  Overall rate : {m.overall_rate:,.0f}/s")
        print(f"  Final offset : {m.current_offset:,}")
        print(f"  Log end      : {m.log_end_offset:,}")
        print(f"  Lag          : {m.lag:,}")

        if self.handlers:
            print("\n  --- Handlers ---")
            print(f"  {'name':<22} {'processed':>10} {'errors':>8} "
                  f"{'avg ms':>9}")
            for h in self.handlers:
                print(f"  {h.name:<22} {h.stats.processed:>10,} "
                      f"{h.stats.errors:>8,} {h.stats.avg_ms:>9.4f}")
                if h.stats.last_error:
                    print(f"    last error: {h.stats.last_error}")

        print("=" * 62 + "\n")