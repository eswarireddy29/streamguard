"""
Generate the synthetic population: customers, cards, merchants, devices.

Everything is driven by a single seeded numpy Generator, so the same
seed always produces the same world. This is the foundation of
reproducible experiments: when a model score changes, it must be the
model that changed, not the data underneath it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import numpy as np
from faker import Faker

from streamguard.generator.reference_data import (
    CARD_TYPES,
    DEVICE_TYPES,
    DOMESTIC_CITIES,
    MERCHANT_CATEGORIES,
    RISK_BANDS,
    City,
    MerchantCategory,
)
from streamguard.utils.geo import jitter_coordinate
from streamguard.utils.logging_config import get_logger

log = get_logger(__name__)
# All customers are in India. Generating in local time means "19:00"
# means 19:00 to the cardholder. PostgreSQL stores timestamptz as UTC
# internally, so nothing is lost.
IST = timezone(timedelta(hours=5, minutes=30))


# ============================================================
#  Plain data containers
# ============================================================
# These are NOT the SQLAlchemy models. Keeping generation separate
# from persistence means we can generate and inspect data without a
# database running, and test the generator without touching Postgres.

@dataclass
class GenCustomer:
    customer_ref: str
    full_name: str
    email: str
    home_city: str
    home_country: str
    home_lat: float
    home_lon: float
    account_opened_at: datetime
    risk_band: str
    avg_monthly_spend: float
    typical_txn_amount: float
    # Behaviour knobs used by the transaction generator in Task 6.
    # Not stored in the database — they describe HOW this customer
    # behaves, and the model must infer that from transactions alone.
    txns_per_day: float = 0.0
    night_owl: float = 0.0
    travel_propensity: float = 0.0
    online_preference: float = 0.0
    category_affinity: dict[str, float] = field(default_factory=dict)


@dataclass
class GenCard:
    card_ref: str
    customer_ref: str
    last_four: str
    card_type: str
    issued_at: datetime
    is_active: bool
    credit_limit: float


@dataclass
class GenMerchant:
    merchant_ref: str
    name: str
    mcc: str
    category: str
    city: str
    country: str
    lat: float
    lon: float
    risk_score: float
    is_online: bool


@dataclass
class GenDevice:
    device_ref: str
    device_type: str
    os_family: str
    fingerprint: str
    first_seen_at: datetime
    is_personal: bool
    owner_ref: str | None  # customer_ref for personal devices, else None


@dataclass
class Population:
    """Everything the transaction generator needs."""
    customers: list[GenCustomer]
    cards: list[GenCard]
    merchants: list[GenMerchant]
    devices: list[GenDevice]

    def summary(self) -> dict[str, int]:
        return {
            "customers": len(self.customers),
            "cards": len(self.cards),
            "merchants": len(self.merchants),
            "devices": len(self.devices),
        }


# ============================================================
#  Helpers
# ============================================================

def _weighted_choice(rng: np.random.Generator, items: list, weights: list[float]):
    """Pick one item with probability proportional to its weight."""
    total = sum(weights)
    probabilities = [w / total for w in weights]
    index = rng.choice(len(items), p=probabilities)
    return items[index]


def _lognormal(rng: np.random.Generator, median: float, sigma: float,
               low: float, high: float) -> float:
    """
    Draw from a lognormal distribution, clipped to [low, high].

    Lognormal because real spending is right-skewed: many small
    amounts, few large ones. The median is the typical value; sigma
    controls how far the tail stretches.
    """
    value = rng.lognormal(mean=np.log(median), sigma=sigma)
    return float(np.clip(value, low, high))


# ============================================================
#  Generators
# ============================================================

class PopulationGenerator:
    """Builds the complete synthetic world from a single seed."""

    def __init__(self, seed: int, simulation_start: datetime | None = None):
        self.seed = seed
        self.rng = np.random.default_rng(seed)
        self.faker = Faker("en_IN")
        # Faker has its own random state — seed it too, or names
        # would differ between runs even with the same numpy seed.
        Faker.seed(seed)

        self.simulation_start = simulation_start or datetime(2026, 1, 1, tzinfo=IST)

    # ---------- Customers ----------

    def generate_customers(self, n: int) -> list[GenCustomer]:
        customers: list[GenCustomer] = []
        city_weights = [c.weight for c in DOMESTIC_CITIES]
        band_names = [b[0] for b in RISK_BANDS]
        band_weights = [b[1] for b in RISK_BANDS]

        for i in range(n):
            city: City = _weighted_choice(self.rng, DOMESTIC_CITIES, city_weights)
            lat, lon = jitter_coordinate(city.lat, city.lon, 12.0, self.rng)

            # Accounts opened between 8 years and 1 month before the
            # simulation starts. Account age is a genuine fraud signal:
            # very new accounts carry more risk.
            days_old = int(self.rng.uniform(30, 8 * 365))
            opened = self.simulation_start - timedelta(days=days_old)

            risk_band = _weighted_choice(self.rng, band_names, band_weights)

            # Monthly spend, long-tailed: median Rs 28,000
            monthly = _lognormal(self.rng, 28_000, 0.85, 3_000, 900_000)
            # How many transactions that spend is spread across
            per_day = float(np.clip(self.rng.gamma(shape=3.0, scale=0.55), 0.3, 9.0))
            typical = monthly / max(per_day * 30.0, 1.0)

            customers.append(
                GenCustomer(
                    customer_ref=f"CUST{i + 1:06d}",
                    full_name=self.faker.name(),
                    email=self.faker.email(),
                    home_city=city.name,
                    home_country=city.country,
                    home_lat=round(lat, 6),
                    home_lon=round(lon, 6),
                    account_opened_at=opened,
                    risk_band=risk_band,
                    avg_monthly_spend=round(monthly, 2),
                    typical_txn_amount=round(typical, 2),
                    txns_per_day=round(per_day, 3),
                    # Fraction of spending that happens late at night
                    night_owl=round(float(self.rng.beta(2, 8)), 3),
                    # Likelihood of transacting away from home city
                    travel_propensity=round(float(self.rng.beta(2, 12)), 3),
                    # Preference for online over in-person
                    online_preference=round(float(self.rng.beta(4, 6)), 3),
                    category_affinity=self._category_affinity(),
                )
            )

        log.info("customers_generated", count=len(customers))
        return customers

    def _category_affinity(self) -> dict[str, float]:
        """
        Each customer prefers some merchant categories over others.

        Without this, every customer would shop uniformly across all
        22 categories and "unusual merchant for this customer" would
        carry no information at all.
        """
        weights = self.rng.dirichlet(np.ones(len(MERCHANT_CATEGORIES)) * 0.6)
        return {
            cat.mcc: round(float(w), 5)
            for cat, w in zip(MERCHANT_CATEGORIES, weights)
        }

    # ---------- Cards ----------

    def generate_cards(self, customers: list[GenCustomer]) -> list[GenCard]:
        cards: list[GenCard] = []
        type_names = [t[0] for t in CARD_TYPES]
        type_weights = [t[1] for t in CARD_TYPES]
        limits = {t[0]: (t[2], t[3]) for t in CARD_TYPES}

        counter = 0
        for customer in customers:
            # Most people hold one or two cards; a few hold three.
            n_cards = int(self.rng.choice([1, 2, 3], p=[0.58, 0.34, 0.08]))

            for _ in range(n_cards):
                counter += 1
                card_type = _weighted_choice(self.rng, type_names, type_weights)
                lo, hi = limits[card_type]

                # A card cannot exist before the account that owns it.
                max_days = max(
                    (self.simulation_start - customer.account_opened_at).days - 1, 1
                )
                issued = customer.account_opened_at + timedelta(
                    days=int(self.rng.uniform(0, max_days))
                )

                cards.append(
                    GenCard(
                        card_ref=f"CARD{counter:07d}",
                        customer_ref=customer.customer_ref,
                        last_four=f"{int(self.rng.integers(0, 10000)):04d}",
                        card_type=card_type,
                        issued_at=issued,
                        is_active=bool(self.rng.random() > 0.03),
                        credit_limit=round(float(self.rng.uniform(lo, hi)), 2),
                    )
                )

        log.info("cards_generated", count=len(cards),
                 per_customer=round(len(cards) / len(customers), 2))
        return cards

    # ---------- Merchants ----------

    def generate_merchants(self, n: int) -> list[GenMerchant]:
        merchants: list[GenMerchant] = []
        city_weights = [c.weight for c in DOMESTIC_CITIES]

        for i in range(n):
            category: MerchantCategory = MERCHANT_CATEGORIES[
                int(self.rng.integers(0, len(MERCHANT_CATEGORIES)))
            ]
            city: City = _weighted_choice(self.rng, DOMESTIC_CITIES, city_weights)
            lat, lon = jitter_coordinate(city.lat, city.lon, 18.0, self.rng)

            is_online = bool(self.rng.random() < category.online_share * 0.5)

            # Individual merchants vary around their category baseline.
            risk = float(np.clip(
                self.rng.normal(category.base_risk, 0.06), 0.005, 0.95
            ))

            merchants.append(
                GenMerchant(
                    merchant_ref=f"MERCH{i + 1:06d}",
                    name=self._merchant_name(category),
                    mcc=category.mcc,
                    category=category.name,
                    city=city.name,
                    country=city.country,
                    lat=round(lat, 6),
                    lon=round(lon, 6),
                    risk_score=round(risk, 4),
                    is_online=is_online,
                )
            )

        log.info("merchants_generated", count=len(merchants))
        return merchants

    def _merchant_name(self, category: MerchantCategory) -> str:
        prefix = self.faker.company().split(",")[0].split(" Ltd")[0]
        short = category.name.split(" & ")[0].split()[0]
        return f"{prefix} {short}"[:160]

    # ---------- Devices ----------

    def generate_devices(self, customers: list[GenCustomer]) -> list[GenDevice]:
        """
        Two kinds of device:
          personal — belongs to one customer (phone, laptop)
          shared   — POS terminals and ATMs used by many people

        The distinction is what makes device-graph features meaningful
        later: a PERSONAL device seen across many unrelated cards is
        suspicious; a POS terminal doing the same is normal.
        """
        devices: list[GenDevice] = []
        personal_types = [d for d in DEVICE_TYPES if d.is_personal]
        shared_types = [d for d in DEVICE_TYPES if not d.is_personal]
        personal_weights = [d.weight for d in personal_types]
        shared_weights = [d.weight for d in shared_types]

        counter = 0

        # 1 to 3 personal devices per customer
        for customer in customers:
            n = int(self.rng.choice([1, 2, 3], p=[0.46, 0.41, 0.13]))
            for _ in range(n):
                counter += 1
                dt = _weighted_choice(self.rng, personal_types, personal_weights)
                first_seen = customer.account_opened_at + timedelta(
                    days=int(self.rng.uniform(0, 400))
                )
                devices.append(
                    GenDevice(
                        device_ref=f"DEV{counter:07d}",
                        device_type=dt.name,
                        os_family=dt.os_family,
                        fingerprint=self.faker.sha256()[:64],
                        first_seen_at=min(first_seen, self.simulation_start),
                        is_personal=True,
                        owner_ref=customer.customer_ref,
                    )
                )

        # Shared terminals — roughly one per 40 customers
        n_shared = max(int(len(customers) / 40), 25)
        for _ in range(n_shared):
            counter += 1
            dt = _weighted_choice(self.rng, shared_types, shared_weights)
            devices.append(
                GenDevice(
                    device_ref=f"DEV{counter:07d}",
                    device_type=dt.name,
                    os_family=dt.os_family,
                    fingerprint=self.faker.sha256()[:64],
                    first_seen_at=self.simulation_start - timedelta(
                        days=int(self.rng.uniform(100, 1500))
                    ),
                    is_personal=False,
                    owner_ref=None,
                )
            )

        log.info("devices_generated", count=len(devices),
                 personal=sum(1 for d in devices if d.is_personal),
                 shared=sum(1 for d in devices if not d.is_personal))
        return devices

    # ---------- Orchestration ----------

    def generate_population(
        self, n_customers: int, n_merchants: int
    ) -> Population:
        log.info("population_generation_started", seed=self.seed,
                 n_customers=n_customers, n_merchants=n_merchants)

        customers = self.generate_customers(n_customers)
        cards = self.generate_cards(customers)
        merchants = self.generate_merchants(n_merchants)
        devices = self.generate_devices(customers)

        population = Population(customers, cards, merchants, devices)
        log.info("population_generation_complete", **population.summary())
        return population