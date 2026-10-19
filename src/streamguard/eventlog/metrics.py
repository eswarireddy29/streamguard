"""
Metrics for the stream processor.

Four things matter when running a stream: how fast are we going, how
far behind are we, how often are we failing, and where is the time
going. Everything here answers one of those.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class ProcessorMetrics:
    """Counters and timings for one processor run."""

    started_at: float = field(default_factory=time.perf_counter)
    events_processed: int = 0
    events_failed: int = 0
    batches: int = 0
    commits: int = 0
    bytes_estimate: int = 0

    # Rolling throughput: events seen since the last sample
    _last_sample_time: float = field(default_factory=time.perf_counter)
    _last_sample_count: int = 0
    recent_rate: float = 0.0

    current_offset: int = 0
    log_end_offset: int = 0

    # ---------- Derived ----------

    @property
    def elapsed(self) -> float:
        return time.perf_counter() - self.started_at

    @property
    def overall_rate(self) -> float:
        """Events per second since the run began."""
        elapsed = self.elapsed
        return self.events_processed / elapsed if elapsed > 0 else 0.0

    @property
    def lag(self) -> int:
        """
        Events not yet processed.

        The single most important number for a streaming system.
        Rising lag means you are losing the race against the stream.
        """
        return max(0, self.log_end_offset - self.current_offset)

    @property
    def error_rate(self) -> float:
        total = self.events_processed + self.events_failed
        return self.events_failed / total if total else 0.0

    @property
    def progress_pct(self) -> float:
        if self.log_end_offset == 0:
            return 100.0
        return 100.0 * self.current_offset / self.log_end_offset

    def eta_seconds(self) -> float | None:
        """Estimated time to drain the log at the current rate."""
        rate = self.recent_rate or self.overall_rate
        if rate <= 0 or self.lag == 0:
            return None
        return self.lag / rate

    # ---------- Sampling ----------

    def sample_rate(self) -> None:
        """
        Update the rolling throughput figure.

        Overall rate flattens out over a long run and hides a
        slowdown. Recent rate shows what is happening NOW, which is
        what you want when something degrades mid-stream.
        """
        now = time.perf_counter()
        window = now - self._last_sample_time
        if window >= 1.0:
            delta = self.events_processed - self._last_sample_count
            self.recent_rate = delta / window
            self._last_sample_time = now
            self._last_sample_count = self.events_processed

    # ---------- Reporting ----------

    def summary(self) -> dict:
        return {
            "events_processed": self.events_processed,
            "events_failed": self.events_failed,
            "error_rate": round(self.error_rate, 6),
            "batches": self.batches,
            "commits": self.commits,
            "elapsed_seconds": round(self.elapsed, 2),
            "overall_rate": round(self.overall_rate, 1),
            "recent_rate": round(self.recent_rate, 1),
            "current_offset": self.current_offset,
            "log_end_offset": self.log_end_offset,
            "lag": self.lag,
        }