"""
Numerically stable running statistics.

Welford's online algorithm maintains mean and variance in a single
pass with O(1) memory per series. We need this because computing
"is this amount unusual for this card?" requires a mean and standard
deviation over the card's history, and storing every amount per card
would grow without bound.

The naive approach (keep sum and sum-of-squares, then
variance = sum_sq/n - mean^2) is algebraically equivalent but
numerically unstable: with large values and small variance the two
terms nearly cancel, destroying precision and sometimes producing a
NEGATIVE variance. Welford avoids the subtraction entirely.

Transaction amounts here span Rs 1 to Rs 500,000, which is exactly
the regime where the naive version degrades.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class RunningStats:
    """Mean, variance and extremes maintained incrementally."""

    count: int = 0
    mean: float = 0.0
    m2: float = 0.0          # sum of squared deviations from the mean
    minimum: float = math.inf
    maximum: float = -math.inf
    total: float = 0.0

    def update(self, value: float) -> None:
        """Incorporate one new observation in O(1)."""
        self.count += 1
        self.total += value

        # Welford's update
        delta = value - self.mean
        self.mean += delta / self.count
        delta2 = value - self.mean      # recomputed AFTER mean moved
        self.m2 += delta * delta2

        if value < self.minimum:
            self.minimum = value
        if value > self.maximum:
            self.maximum = value

    @property
    def variance(self) -> float:
        """Sample variance. Needs at least two observations."""
        if self.count < 2:
            return 0.0
        return self.m2 / (self.count - 1)

    @property
    def std(self) -> float:
        return math.sqrt(self.variance)

    def z_score(self, value: float) -> float:
        """
        How many standard deviations this value sits from the mean.

        Returns 0.0 when there is not enough history, or when every
        observation so far was identical (std = 0). Returning 0 rather
        than infinity is deliberate: "no information" should read as
        "unremarkable", not as an extreme signal the model would
        latch onto.
        """
        if self.count < 2:
            return 0.0
        std = self.std
        if std < 1e-9:
            return 0.0
        return (value - self.mean) / std

    def ratio_to_mean(self, value: float) -> float:
        """Value as a multiple of the running mean."""
        if self.count == 0 or abs(self.mean) < 1e-9:
            return 1.0
        return value / self.mean

    def to_dict(self) -> dict[str, float]:
        return {
            "count": self.count,
            "mean": round(self.mean, 4),
            "std": round(self.std, 4),
            "min": self.minimum if self.count else 0.0,
            "max": self.maximum if self.count else 0.0,
            "total": round(self.total, 2),
        }


@dataclass
class ExponentialMovingAverage:
    """
    An average that weights recent observations more heavily.

    alpha controls the decay: higher means faster adaptation to
    change. Useful alongside RunningStats because a plain mean over
    all history is slow to notice that a customer's spending has
    genuinely shifted -- and we want the model to distinguish a real
    change from a one-off anomaly.
    """

    alpha: float = 0.1
    value: float = 0.0
    initialised: bool = False

    def update(self, observation: float) -> None:
        if not self.initialised:
            self.value = observation
            self.initialised = True
        else:
            self.value = self.alpha * observation + (1 - self.alpha) * self.value

    def ratio(self, observation: float) -> float:
        if not self.initialised or abs(self.value) < 1e-9:
            return 1.0
        return observation / self.value