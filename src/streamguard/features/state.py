"""
Bounded per-entity state for online feature computation.

Memory stays CONSTANT regardless of stream length. Each card keeps a
short deque of recent transactions plus running aggregates; nothing
grows without limit.

THE RULE, enforced structurally by separating these methods:

    1. compute features FROM state   (state holds only the past)
    2. THEN update state WITH the event

Calling them in the other order would let a transaction contribute to
its own statistics -- its amount leaking into its own z-score. That is
look-ahead leakage, and it is silent: no error, just numbers that are
too good to be true.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from streamguard.features.stats import ExponentialMovingAverage, RunningStats

# How many recent transactions to keep per card. 50 covers every
# window we compute (the longest is 24h, and no card in this dataset
# exceeds ~50 transactions in 24h). Larger would waste memory;
# smaller would silently truncate the 24h window.
RECENT_WINDOW = 50

# Cap on distinct values tracked per card, so a pathological card
# cannot grow its state without bound.
MAX_TRACKED_VALUES = 200


@dataclass(frozen=True)
class TransactionMemory:
    """
    The minimum needed from a past transaction to compute features.

    Deliberately NOT the whole payload: storing full events for 7,532
    cards would multiply memory by roughly twenty for no benefit.
    """
    occurred_at: datetime
    amount: float
    lat: float
    lon: float
    merchant_ref: str
    mcc: str
    city: str
    channel: str


@dataclass
class CardState:
    """Everything remembered about one card."""

    card_ref: str

    # Recent transactions, newest last. maxlen makes eviction automatic.
    recent: deque[TransactionMemory] = field(
        default_factory=lambda: deque(maxlen=RECENT_WINDOW)
    )

    # Running aggregates over the card's full history
    amount_stats: RunningStats = field(default_factory=RunningStats)
    amount_ema: ExponentialMovingAverage = field(
        default_factory=lambda: ExponentialMovingAverage(alpha=0.15)
    )

    # Distinct values seen, for novelty features
    seen_merchants: set[str] = field(default_factory=set)
    seen_mccs: set[str] = field(default_factory=set)
    seen_cities: set[str] = field(default_factory=set)
    seen_devices: set[str] = field(default_factory=set)
    seen_countries: set[str] = field(default_factory=set)

    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    total_count: int = 0

    # ---------- Reading (features) ----------

    def count_within(self, now: datetime, window: timedelta) -> int:
        """
        How many past transactions fall inside the window ending now.

        Counts backwards and stops at the first one outside the
        window, since `recent` is ordered.
        """
        cutoff = now - window
        count = 0
        for memory in reversed(self.recent):
            if memory.occurred_at < cutoff:
                break
            count += 1
        return count

    def sum_within(self, now: datetime, window: timedelta) -> float:
        cutoff = now - window
        total = 0.0
        for memory in reversed(self.recent):
            if memory.occurred_at < cutoff:
                break
            total += memory.amount
        return total

    def distinct_within(
        self, now: datetime, window: timedelta, attribute: str
    ) -> int:
        """Distinct values of one attribute inside the window."""
        cutoff = now - window
        values = set()
        for memory in reversed(self.recent):
            if memory.occurred_at < cutoff:
                break
            values.add(getattr(memory, attribute))
        return len(values)

    @property
    def previous(self) -> TransactionMemory | None:
        """The most recent past transaction, or None if this is the first."""
        return self.recent[-1] if self.recent else None

    def age_days(self, now: datetime) -> float:
        """How long this card has been active, in days."""
        if self.first_seen_at is None:
            return 0.0
        return (now - self.first_seen_at).total_seconds() / 86400.0

    # ---------- Writing (state update) ----------

    def update(self, memory: TransactionMemory, device_ref: str | None,
               country: str) -> None:
        """
        Fold one transaction into the state.

        MUST be called AFTER features have been computed.
        """
        self.recent.append(memory)
        self.amount_stats.update(memory.amount)
        self.amount_ema.update(memory.amount)

        # Bounded sets: stop adding once the cap is reached, so a
        # pathological card cannot grow state without limit.
        if len(self.seen_merchants) < MAX_TRACKED_VALUES:
            self.seen_merchants.add(memory.merchant_ref)
        if len(self.seen_mccs) < MAX_TRACKED_VALUES:
            self.seen_mccs.add(memory.mcc)
        if len(self.seen_cities) < MAX_TRACKED_VALUES:
            self.seen_cities.add(memory.city)
        if len(self.seen_countries) < MAX_TRACKED_VALUES:
            self.seen_countries.add(country)
        if device_ref and len(self.seen_devices) < MAX_TRACKED_VALUES:
            self.seen_devices.add(device_ref)

        if self.first_seen_at is None:
            self.first_seen_at = memory.occurred_at
        self.last_seen_at = memory.occurred_at
        self.total_count += 1


@dataclass
class MerchantState:
    """
    Aggregates per merchant.

    Merchant collusion is almost invisible per transaction -- the
    cardholder behaves normally and the merchant is the anomaly. It
    only shows up in merchant-level statistics, which is why this
    exists.
    """

    merchant_ref: str
    amount_stats: RunningStats = field(default_factory=RunningStats)
    distinct_cards: set[str] = field(default_factory=set)
    total_count: int = 0

    def update(self, amount: float, card_ref: str) -> None:
        self.amount_stats.update(amount)
        if len(self.distinct_cards) < 10_000:
            self.distinct_cards.add(card_ref)
        self.total_count += 1


@dataclass
class CustomerState:
    """Aggregates across all of a customer's cards."""

    customer_ref: str
    amount_stats: RunningStats = field(default_factory=RunningStats)
    seen_cards: set[str] = field(default_factory=set)
    total_count: int = 0

    def update(self, amount: float, card_ref: str) -> None:
        self.amount_stats.update(amount)
        self.seen_cards.add(card_ref)
        self.total_count += 1


class StateStore:
    """
    Holds state for every entity seen so far.

    Dictionaries keyed by business reference. Memory is bounded by the
    NUMBER OF ENTITIES (7,532 cards, 800 merchants, 5,000 customers),
    not by the number of events -- which is what makes this viable on
    8 GB for a stream of any length.
    """

    def __init__(self) -> None:
        self.cards: dict[str, CardState] = {}
        self.merchants: dict[str, MerchantState] = {}
        self.customers: dict[str, CustomerState] = {}

    def card(self, card_ref: str) -> CardState:
        state = self.cards.get(card_ref)
        if state is None:
            state = CardState(card_ref=card_ref)
            self.cards[card_ref] = state
        return state

    def merchant(self, merchant_ref: str) -> MerchantState:
        state = self.merchants.get(merchant_ref)
        if state is None:
            state = MerchantState(merchant_ref=merchant_ref)
            self.merchants[merchant_ref] = state
        return state

    def customer(self, customer_ref: str) -> CustomerState:
        state = self.customers.get(customer_ref)
        if state is None:
            state = CustomerState(customer_ref=customer_ref)
            self.customers[customer_ref] = state
        return state

    def summary(self) -> dict[str, int]:
        return {
            "cards": len(self.cards),
            "merchants": len(self.merchants),
            "customers": len(self.customers),
            "total_card_events": sum(c.total_count for c in self.cards.values()),
        }

    def clear(self) -> None:
        """Reset everything. Essential before a replay."""
        self.cards.clear()
        self.merchants.clear()
        self.customers.clear()