"""
src/streamguard/features/graph.py

Task 18A - features from the card-merchant-device network.

The 49 existing features describe ONE transaction and ONE card's own
history. They cannot see that this card and that card both used the
same device last week. Fraud rings share infrastructure, and that
sharing is only visible in the network.

THE GOVERNING RULE STILL HOLDS: a feature at time T may use only edges
added before T. The graph is built incrementally as events arrive, in
the same order the stream delivers them, so a day-10 feature cannot
know about day 80.

8 GB note: this stores adjacency as dicts of sets, not a NetworkX
object per transaction. NetworkX is used only for the component
analysis in the offline summary, where it runs once.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np

# Ordered contract, same idea as FEATURE_NAMES in computer.py.
GRAPH_FEATURE_NAMES = [
    "device_card_count",        # how many cards this device has served
    "device_card_count_7d",     # ... in the last 7 days
    "merchant_card_count_7d",   # how many cards this merchant served, 7d
    "card_device_count",        # how many devices this card has used
    "card_merchant_count_7d",   # how many merchants this card used, 7d
    "device_shared",            # 1 if this device has served >1 card
    "device_new_card",          # 1 if this card is new to this device
    "merchant_new_card",        # 1 if this card is new to this merchant
    "device_card_velocity_1h",  # distinct cards on this device in 1h
    "merchant_card_velocity_1h",
    "ring_size",                # cards reachable via shared devices
    "ring_fraud_density",       # placeholder - see note below
]


@dataclass
class _TimedSet:
    """A set of ids with timestamps, pruned to a time window.

    Used for "distinct cards on this device in the last hour". A plain
    set would grow forever; this bounds memory by the window, not by
    total event count.
    """
    window: timedelta
    items: deque = field(default_factory=deque)   # (timestamp, id)

    def add(self, when: datetime, item: str) -> None:
        self.items.append((when, item))

    def prune(self, now: datetime) -> None:
        cutoff = now - self.window
        while self.items and self.items[0][0] < cutoff:
            self.items.popleft()

    def distinct(self, now: datetime) -> int:
        self.prune(now)
        return len({i for _, i in self.items})


class TransactionGraph:
    """Incrementally built card-merchant-device network.

    Mirrors the FeatureComputer contract from Task 10:
        compute()  reads the graph        (no mutation)
        update()   writes to the graph    (no reading for features)
        process()  is the only place the order is fixed

    That separation is what makes look-ahead leakage structurally
    impossible rather than merely unlikely.
    """

    def __init__(self, ring_hops: int = 2, ring_cap: int = 200):
        # Lifetime adjacency.
        self.device_cards: dict[str, set] = defaultdict(set)
        self.card_devices: dict[str, set] = defaultdict(set)
        self.merchant_cards: dict[str, set] = defaultdict(set)
        self.card_merchants: dict[str, set] = defaultdict(set)

        # Windowed adjacency.
        self.device_cards_7d: dict[str, _TimedSet] = {}
        self.merchant_cards_7d: dict[str, _TimedSet] = {}
        self.card_merchants_7d: dict[str, _TimedSet] = {}
        self.device_cards_1h: dict[str, _TimedSet] = {}
        self.merchant_cards_1h: dict[str, _TimedSet] = {}

        # Breadth-first search depth for ring detection, and a hard cap
        # so one hub device cannot make every traversal O(n).
        self.ring_hops = ring_hops
        self.ring_cap = ring_cap

    # ---------- internals ----------

    def _timed(self, store: dict, key: str, window: timedelta) -> _TimedSet:
        ts = store.get(key)
        if ts is None:
            ts = _TimedSet(window=window)
            store[key] = ts
        return ts

    def _ring_size(self, card: str) -> int:
        """Cards reachable from this one within ring_hops, via shared
        devices and merchants.

        A fraud ring using one device across many cards shows up as a
        large value here. Capped at ring_cap because a popular public
        terminal would otherwise connect thousands of innocent cards -
        which is itself a limitation worth stating in the report.
        """
        seen = {card}
        frontier = {card}

        for _ in range(self.ring_hops):
            nxt = set()
            for c in frontier:
                for d in self.card_devices.get(c, ()):
                    nxt |= self.device_cards.get(d, set())
                    if len(seen) + len(nxt) > self.ring_cap:
                        return self.ring_cap
            nxt -= seen
            if not nxt:
                break
            seen |= nxt
            frontier = nxt

        return min(len(seen), self.ring_cap)

    # ---------- the contract ----------

    def compute(self, card: str, merchant: str, device: str | None,
                when: datetime) -> dict:
        """Graph features for this transaction, using only PAST edges.

        Reads only. Never mutates. Call this BEFORE update().
        """
        dev_cards = self.device_cards.get(device, set()) if device else set()
        mer_cards = self.merchant_cards.get(merchant, set())

        d7 = (self._timed(self.device_cards_7d, device, timedelta(days=7))
              if device else None)
        m7 = self._timed(self.merchant_cards_7d, merchant, timedelta(days=7))
        cm7 = self._timed(self.card_merchants_7d, card, timedelta(days=7))
        d1 = (self._timed(self.device_cards_1h, device, timedelta(hours=1))
              if device else None)
        m1 = self._timed(self.merchant_cards_1h, merchant, timedelta(hours=1))

        return {
            "device_card_count": float(len(dev_cards)),
            "device_card_count_7d": float(d7.distinct(when)) if d7 else 0.0,
            "merchant_card_count_7d": float(m7.distinct(when)),
            "card_device_count": float(len(self.card_devices.get(card, set()))),
            "card_merchant_count_7d": float(cm7.distinct(when)),
            "device_shared": 1.0 if len(dev_cards) > 1 else 0.0,
            "device_new_card": 0.0 if card in dev_cards else 1.0,
            "merchant_new_card": 0.0 if card in mer_cards else 1.0,
            "device_card_velocity_1h": float(d1.distinct(when)) if d1 else 0.0,
            "merchant_card_velocity_1h": float(m1.distinct(when)),
            "ring_size": float(self._ring_size(card)),
            # Deliberately 0.0: filling this from labels would be
            # leakage. In production it would come from CONFIRMED
            # analyst verdicts on past cases, which is a Task 30 input.
            "ring_fraud_density": 0.0,
        }

    def update(self, card: str, merchant: str, device: str | None,
               when: datetime) -> None:
        """Add this transaction's edges. Call AFTER compute()."""
        self.merchant_cards[merchant].add(card)
        self.card_merchants[card].add(merchant)
        self._timed(self.merchant_cards_7d, merchant, timedelta(days=7)).add(when, card)
        self._timed(self.card_merchants_7d, card, timedelta(days=7)).add(when, merchant)
        self._timed(self.merchant_cards_1h, merchant, timedelta(hours=1)).add(when, card)

        if device:
            self.device_cards[device].add(card)
            self.card_devices[card].add(device)
            self._timed(self.device_cards_7d, device, timedelta(days=7)).add(when, card)
            self._timed(self.device_cards_1h, device, timedelta(hours=1)).add(when, card)

    def process(self, card: str, merchant: str, device: str | None,
                when: datetime) -> dict:
        """compute() then update(), in that order. The only correct order."""
        features = self.compute(card, merchant, device, when)
        self.update(card, merchant, device, when)
        return features

    def stats(self) -> dict:
        """Size of the graph, for the build report."""
        return {
            "cards": len(self.card_devices) or len(self.card_merchants),
            "devices": len(self.device_cards),
            "merchants": len(self.merchant_cards),
            "card_device_edges": sum(len(v) for v in self.card_devices.values()),
            "card_merchant_edges": sum(len(v) for v in self.card_merchants.values()),
            "shared_devices": sum(1 for v in self.device_cards.values() if len(v) > 1),
        }