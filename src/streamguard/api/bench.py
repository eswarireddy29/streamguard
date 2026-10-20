"""
src/streamguard/api/bench.py

Task 20 - measure the latency budget instead of guessing it.
"""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass, asdict, field

import numpy as np


@dataclass
class LatencyStats:
    """Percentiles for one stage or one path."""
    label: str
    n: int
    mean_ms: float
    p50_ms: float
    p90_ms: float
    p95_ms: float
    p99_ms: float
    max_ms: float
    min_ms: float
    throughput_per_sec: float

    def to_dict(self) -> dict:
        return asdict(self)

    def line(self) -> str:
        return (f"  {self.label:<26}{self.n:>7,}"
                f"{self.p50_ms:>9.2f}{self.p95_ms:>9.2f}"
                f"{self.p99_ms:>9.2f}{self.max_ms:>9.2f}"
                f"{self.throughput_per_sec:>11,.0f}")


def summarize(label: str, samples_ms: list) -> LatencyStats:
    """Percentiles, not just the mean.

    The mean hides the tail. A service with a 3 ms mean and a 400 ms
    p99 fails 1 request in 100, and that is the one the customer
    notices at the checkout.
    """
    s = sorted(samples_ms)
    n = len(s)
    if n == 0:
        return LatencyStats(label, 0, *[0.0] * 7)

    def pct(p: float) -> float:
        k = max(0, min(n - 1, int(round(p / 100 * (n - 1)))))
        return float(s[k])

    mean = float(statistics.fmean(s))
    return LatencyStats(
        label=label,
        n=n,
        mean_ms=mean,
        p50_ms=pct(50),
        p90_ms=pct(90),
        p95_ms=pct(95),
        p99_ms=pct(99),
        max_ms=float(s[-1]),
        min_ms=float(s[0]),
        throughput_per_sec=(1000.0 / mean) if mean else 0.0,
    )


@dataclass
class StageTimer:
    """Times each stage of scoring separately.

    A single end-to-end number tells you whether the budget is met. It
    does not tell you WHICH stage to fix. These are the four candidates:
    feature computation, graph lookup, model prediction, SHAP.
    """
    stages: dict = field(default_factory=lambda: {
        "features": [], "graph": [], "predict": [], "shap": [], "total": [],
    })

    def record(self, stage: str, ms: float) -> None:
        self.stages.setdefault(stage, []).append(ms)

    def report(self) -> list:
        return [summarize(k, v) for k, v in self.stages.items() if v]


HEADER = (f"  {'stage':<26}{'n':>7}{'p50':>9}{'p95':>9}"
          f"{'p99':>9}{'max':>9}{'per sec':>11}")
RULE = "  " + "-" * 80