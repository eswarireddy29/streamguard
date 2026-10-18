"""
Generate normal (non-fraudulent) transaction activity.

Streams day by day so memory stays flat regardless of simulation
length, and produces transactions in chronological order, which the
feature engine depends on.

Fraud is NOT injected here -- that is Task 7, deliberately separate.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import numpy as np
from streamguard.db.models import Channel, EntryMode, FraudType
from streamguard.generator.entities import Population
from streamguard.generator.patterns import (
    dow_multiplier,
    merchant_selection_weights,
    sample_amount,
    sample_hour,
    sample_second_within_hour,
)
from streamguard.generator.reference_data import MERCHANT_CATEGORIES
from streamguard.utils.geo import haversine_km, jitter_coordinate
from streamguard.utils.logging_config import get_logger

log = get_logger(__name__)
# All customers are in India. Transactions are generated in local
# time so "19:00" means 19:00 to the cardholder. PostgreSQL stores
# timestamptz as UTC internally; nothing is lost.
IST = timezone(timedelta(hours=5, minutes=30))

CATEGORY_BY_MCC = {c.mcc: c for c in MERCHANT_CATEGORIES}


@dataclass
class GenTransaction:
    """One payment event, before it reaches the database."""
    transaction_ref: str
    occurred_at: datetime
    card_ref: str
    customer_ref: str
    merchant_ref: str
    device_ref: str | None
    amount: float
    currency: str
    channel: str
    entry_mode: str
    city: str
    country: str
    lat: float
    lon: float
    is_fraud: bool
    fraud_type: str


class TransactionGenerator:
    """Produces normal transaction activity for a population."""

    def __init__(
        self,
        population: Population,
        seed: int,
        simulation_start: datetime | None = None,
    ):
        self.population = population
        self.rng = np.random.default_rng(seed + 1_000_003)  # distinct stream
        self.start = simulation_start or datetime(2026, 1, 1, tzinfo=IST)
        self._counter = 0

        self._build_indexes()

    # ---------- Pre-computation ----------

    def _build_indexes(self) -> None:
        """
        Pre-compute lookup arrays once.

        Doing this per transaction would mean 700,000 rebuilds of the
        same arrays. Building once turns merchant selection from the
        bottleneck into a single vectorised operation.
        """
        merchants = self.population.merchants

        self.merchant_refs = np.array([m.merchant_ref for m in merchants])
        self.merchant_mccs = np.array([m.mcc for m in merchants])
        self.merchant_lats = np.array([m.lat for m in merchants])
        self.merchant_lons = np.array([m.lon for m in merchants])
        self.merchant_online = np.array([m.is_online for m in merchants])
        self.merchant_cities = np.array([m.city for m in merchants])
        self.merchant_countries = np.array([m.country for m in merchants])

        # Cards grouped by their owner
        self.cards_by_customer: dict[str, list] = {}
        for card in self.population.cards:
            if card.is_active:
                self.cards_by_customer.setdefault(card.customer_ref, []).append(card)

        # Personal devices grouped by their owner
        self.devices_by_customer: dict[str, list[str]] = {}
        self.shared_devices: list[str] = []
        for device in self.population.devices:
            if device.is_personal and device.owner_ref:
                self.devices_by_customer.setdefault(
                    device.owner_ref, []
                ).append(device.device_ref)
            elif not device.is_personal:
                self.shared_devices.append(device.device_ref)

        # Only customers who actually hold an active card can transact
        self.active_customers = [
            c for c in self.population.customers
            if c.customer_ref in self.cards_by_customer
        ]

        # Distance from every customer's home to every merchant, computed
        # once. 5000 x 800 floats is ~32 MB -- acceptable, and it removes
        # 700,000 repeated distance calculations.
        self.distance_cache: dict[str, np.ndarray] = {}
        for customer in self.active_customers:
            self.distance_cache[customer.customer_ref] = self._distances_from(
                customer.home_lat, customer.home_lon
            )

        log.info(
            "generator_indexes_built",
            merchants=len(merchants),
            active_customers=len(self.active_customers),
            shared_devices=len(self.shared_devices),
        )

    def _distances_from(self, lat: float, lon: float) -> np.ndarray:
        """Vectorised haversine from one point to every merchant."""
        phi1 = np.radians(lat)
        phi2 = np.radians(self.merchant_lats)
        d_phi = np.radians(self.merchant_lats - lat)
        d_lambda = np.radians(self.merchant_lons - lon)

        a = (
            np.sin(d_phi / 2) ** 2
            + np.cos(phi1) * np.cos(phi2) * np.sin(d_lambda / 2) ** 2
        )
        return 2 * 6371.0 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))

    # ---------- Per-day generation ----------

    def generate_day(self, day_index: int) -> list[GenTransaction]:
        """Produce every normal transaction for one simulated day."""
        day_start = self.start + timedelta(days=day_index)
        weekday = day_start.weekday()
        transactions: list[GenTransaction] = []

        for customer in self.active_customers:
            n = self._transaction_count_for_day(customer, weekday)
            for _ in range(n):
                txn = self._make_transaction(customer, day_start)
                if txn is not None:
                    transactions.append(txn)

        # Sort within the day so output is strictly chronological
        transactions.sort(key=lambda t: t.occurred_at)
        return transactions

    def _transaction_count_for_day(self, customer, weekday: int) -> int:
        """
        How many transactions this customer makes today.

        Poisson, because it models "number of independent events in a
        fixed interval" -- exactly what this is. The rate is the
        customer's own daily rate, adjusted for the day of week.
        """
        rate = customer.txns_per_day * dow_multiplier("", weekday)
        return int(self.rng.poisson(rate))

    def _make_transaction(self, customer, day_start: datetime) -> GenTransaction | None:
        # --- Which merchant? ---
        distances = self.distance_cache[customer.customer_ref]
        weights = merchant_selection_weights(
            customer.category_affinity,
            self.merchant_mccs,
            distances,
            self.merchant_online,
            customer.online_preference,
        )
        idx = int(self.rng.choice(len(self.merchant_refs), p=weights))

        merchant_ref = str(self.merchant_refs[idx])
        mcc = str(self.merchant_mccs[idx])
        category = CATEGORY_BY_MCC[mcc]
        is_online = bool(self.merchant_online[idx])

        # --- When? ---
        hour = sample_hour(self.rng, mcc, customer.night_owl)
        minute, second = sample_second_within_hour(self.rng)
        occurred_at = day_start.replace(hour=hour, minute=minute, second=second)

        # --- How much? ---
        amount = sample_amount(self.rng, category, customer.typical_txn_amount)

        # --- Where? ---
        if is_online:
            # An online purchase happens where the CUSTOMER is,
            # not where the merchant is registered.
            city, country = customer.home_city, customer.home_country
            lat, lon = jitter_coordinate(
                customer.home_lat, customer.home_lon, 3.0, self.rng
            )
        else:
            city = str(self.merchant_cities[idx])
            country = str(self.merchant_countries[idx])
            lat, lon = jitter_coordinate(
                float(self.merchant_lats[idx]),
                float(self.merchant_lons[idx]),
                1.5,
                self.rng,
            )

        # --- Channel and entry mode ---
        channel, entry_mode = self._channel_and_entry(category, is_online)

        # --- Card and device ---
        cards = self.cards_by_customer[customer.customer_ref]
        card = cards[int(self.rng.integers(0, len(cards)))]
        device_ref = self._choose_device(customer, channel)

        self._counter += 1

        return GenTransaction(
            transaction_ref=f"TXN{self._counter:010d}",
            occurred_at=occurred_at,
            card_ref=card.card_ref,
            customer_ref=customer.customer_ref,
            merchant_ref=merchant_ref,
            device_ref=device_ref,
            amount=amount,
            currency="INR" if country == "IN" else "USD",
            channel=channel.value,
            entry_mode=entry_mode.value,
            city=city,
            country=country,
            lat=round(lat, 6),
            lon=round(lon, 6),
            is_fraud=False,
            fraud_type=FraudType.NONE.value,
        )

    def _channel_and_entry(self, category, is_online: bool):
        """Pick a plausible channel and entry mode for this category."""
        if category.recurring and self.rng.random() < 0.65:
            return Channel.RECURRING, EntryMode.STORED_CREDENTIAL

        if is_online or self.rng.random() < category.online_share:
            return Channel.ECOMMERCE, EntryMode.STORED_CREDENTIAL

        draw = self.rng.random()
        if draw < 0.42:
            return Channel.CONTACTLESS, EntryMode.NFC
        if draw < 0.92:
            return Channel.POS, EntryMode.CHIP
        return Channel.POS, EntryMode.SWIPE

    def _choose_device(self, customer, channel: Channel) -> str | None:
        """
        Online payments come from the customer's own device.
        In-person payments go through a shared terminal.
        """
        if channel in (Channel.ECOMMERCE, Channel.RECURRING):
            owned = self.devices_by_customer.get(customer.customer_ref)
            if owned:
                return owned[int(self.rng.integers(0, len(owned)))]
            return None

        if self.shared_devices and self.rng.random() < 0.85:
            return self.shared_devices[
                int(self.rng.integers(0, len(self.shared_devices)))
            ]
        return None

    # ---------- Streaming interface ----------

    def stream_days(self, n_days: int) -> Iterator[tuple[int, list[GenTransaction]]]:
        """
        Yield one day of transactions at a time.

        This is what keeps memory flat: the caller inserts each day
        and lets it be garbage collected before the next is built.
        """
        for day in range(n_days):
            transactions = self.generate_day(day)
            yield day, transactions