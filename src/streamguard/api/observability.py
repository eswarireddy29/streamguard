"""
src/streamguard/api/observability.py

Task 31 - what is the service doing right now?

The Task 19 /health endpoint answers "is it up". That is not enough
to run anything: when latency doubles at 3am you need to know WHICH
stage slowed, whether errors are rising, and how long the queue of
in-flight requests is. Those questions cannot be answered after the
fact from a log file.

DESIGN CONSTRAINTS, because this runs inside the latency budget:

  - Bounded memory. A deque of the last N latencies, not a growing
    list. An observability system that leaks memory eventually takes
    down the thing it was watching.

  - No locks on the hot path. Python's GIL makes appends to a deque
    atomic enough for counters; exact accuracy under concurrency is
    not worth a lock inside a 2ms request.

  - Percentiles computed ON READ, not on write. Sorting on every
    request would cost more than the request.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field

import numpy as np


# The last N requests. 10,000 at ~8 bytes a float is 80KB - bounded
# and small enough to ignore on an 8GB machine.
WINDOW = 10_000


@dataclass
class StageTimings:
    """Latency per stage, so a slowdown can be attributed."""
    features: deque = field(default_factory=lambda: deque(maxlen=WINDOW))
    graph: deque = field(default_factory=lambda: deque(maxlen=WINDOW))
    predict: deque = field(default_factory=lambda: deque(maxlen=WINDOW))
    shap: deque = field(default_factory=lambda: deque(maxlen=WINDOW))
    total: deque = field(default_factory=lambda: deque(maxlen=WINDOW))

    def record(self, stage: str, ms: float) -> None:
        d = getattr(self, stage, None)
        if d is not None:
            d.append(ms)


def percentiles(values) -> dict:
    """p50/p95/p99 from a window of samples.

    Computed on read. Sorting 10,000 floats takes under a millisecond
    and happens only when someone asks, rather than on every request.
    """
    if not values:
        return {"n": 0, "p50": 0.0, "p95": 0.0, "p99": 0.0,
                "max": 0.0, "mean": 0.0}
    arr = np.fromiter(values, dtype=float)
    return {
        "n": int(arr.size),
        "p50": float(np.percentile(arr, 50)),
        "p95": float(np.percentile(arr, 95)),
        "p99": float(np.percentile(arr, 99)),
        "max": float(arr.max()),
        "mean": float(arr.mean()),
    }


class Metrics:
    """Counters and latency windows for the whole service."""

    def __init__(self):
        self.started = time.time()
        self.stages = StageTimings()

        # Counters. Monotonic, so a dashboard can take differences.
        self.requests = defaultdict(int)       # by endpoint
        self.statuses = defaultdict(int)       # by status code
        self.decisions = defaultdict(int)      # approve/review/block
        self.errors = defaultdict(int)         # by exception type

        # In-flight: incremented on entry, decremented on exit. A
        # rising value with flat throughput means requests are
        # queueing - the earliest visible sign of saturation.
        self.in_flight = 0
        self.max_in_flight = 0

        self.duplicates = 0
        self.persist_failures = 0

    # ---------- recording ----------

    def start_request(self, endpoint: str) -> float:
        self.requests[endpoint] += 1
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        return time.perf_counter()

    def end_request(self, endpoint: str, started: float,
                    status: int = 200) -> float:
        self.in_flight = max(0, self.in_flight - 1)
        self.statuses[status] += 1
        elapsed_ms = (time.perf_counter() - started) * 1000
        self.stages.record("total", elapsed_ms)
        return elapsed_ms

    def record_stage(self, stage: str, ms: float) -> None:
        self.stages.record(stage, ms)

    def record_decision(self, decision: str) -> None:
        self.decisions[decision] += 1

    def record_error(self, kind: str) -> None:
        self.errors[kind] += 1

    # ---------- reporting ----------

    def snapshot(self) -> dict:
        uptime = time.time() - self.started
        total_requests = sum(self.requests.values())
        total_errors = sum(self.errors.values())
        total_decisions = sum(self.decisions.values())
        flagged = self.decisions.get("review", 0) + self.decisions.get("block", 0)

        return {
            "uptime_seconds": round(uptime, 1),
            "requests": {
                "total": total_requests,
                "by_endpoint": dict(self.requests),
                "by_status": {str(k): v for k, v in self.statuses.items()},
                "per_second": round(total_requests / uptime, 2) if uptime else 0,
            },
            "latency_ms": {
                stage: percentiles(getattr(self.stages, stage))
                for stage in ("total", "features", "graph", "predict", "shap")
            },
            "decisions": {
                "counts": dict(self.decisions),
                "total": total_decisions,
                "flagged_pct": round(100 * flagged / total_decisions, 3)
                               if total_decisions else 0.0,
            },
            "errors": {
                "total": total_errors,
                "by_type": dict(self.errors),
                # The number an alert should watch. A rising rate is a
                # symptom; a single error is noise.
                "rate": round(total_errors / total_requests, 5)
                        if total_requests else 0.0,
            },
            "saturation": {
                "in_flight": self.in_flight,
                "max_in_flight": self.max_in_flight,
                "duplicates_rejected": self.duplicates,
                "persist_failures": self.persist_failures,
            },
        }

    def prometheus(self) -> str:
        """Text in Prometheus exposition format.

        Not because Prometheus is running - it is not, and installing
        it would break the zero-rupee constraint. The format is here
        because it is what a scraper expects, and emitting it means
        the service is ready for one without a rewrite.
        """
        s = self.snapshot()
        lines = []

        def metric(name, value, help_text, mtype="gauge", labels=""):
            lines.append(f"# HELP {name} {help_text}")
            lines.append(f"# TYPE {name} {mtype}")
            lines.append(f"{name}{labels} {value}")

        metric("streamguard_uptime_seconds", s["uptime_seconds"],
               "Seconds since the service started")
        metric("streamguard_requests_total", s["requests"]["total"],
               "Total HTTP requests", "counter")
        metric("streamguard_errors_total", s["errors"]["total"],
               "Total errors", "counter")
        metric("streamguard_in_flight", s["saturation"]["in_flight"],
               "Requests currently being handled")

        for stage, p in s["latency_ms"].items():
            for q in ("p50", "p95", "p99"):
                lines.append(
                    f'streamguard_latency_ms{{stage="{stage}",quantile="{q}"}} '
                    f'{p[q]}')

        for decision, n in s["decisions"]["counts"].items():
            lines.append(
                f'streamguard_decisions_total{{decision="{decision}"}} {n}')

        for status, n in s["requests"]["by_status"].items():
            lines.append(
                f'streamguard_responses_total{{status="{status}"}} {n}')

        return "\n".join(lines) + "\n"


# One instance for the process. Option A (Task 19) already means one
# process holds the feature state, so a module-level singleton matches
# the architecture rather than fighting it.
metrics = Metrics()