"""
Inject fraud episodes into a stream of normal transactions.

A fraud EPISODE is a burst of related fraudulent transactions on one
card: a fraudster does not make a single purchase and vanish. Each
episode is anchored at a point in time and produces several rows.

Episodes are generated independently of normal activity, then merged
into the day's stream in chronological order.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np

from streamguard.db.models import Channel, EntryMode, FraudType
from streamguard.generator.entities import Population
from streamguard.generator.fraud_patterns import (
    ATO_MERCHANT_MAX_KM,
    COLLUSION_MERCHANT_MAX_KM,
    ATO_NEW_DEVICE_PROB,
    CARD_TESTING_JITTER_KM,
    CARD_TESTING_NEW_DEVICE_PROB,
    CNP_NEW_DEVICE_PROB,
    COLLUSION_NEW_DEVICE_PROB,
    COLLUSION_POS_SHARE,
    GEO_NEW_DEVICE_PROB,
    GEO_POS_SHARE,
    ATO_AMOUNT_MULTIPLIER_MAX,
    ATO_AMOUNT_MULTIPLIER_MIN,
    ATO_GAP_MINUTES_MAX,
    ATO_GAP_MINUTES_MIN,
    CARD_TESTING_AMOUNT_MAX,
    CARD_TESTING_AMOUNT_MIN,
    CARD_TESTING_GAP_SECONDS_MAX,
    CARD_TESTING_GAP_SECONDS_MIN,
    CNP_AMOUNT_MULTIPLIER_MAX,
    CNP_AMOUNT_MULTIPLIER_MIN,
    CNP_GAP_MINUTES_MAX,
    CNP_GAP_MINUTES_MIN,
    COLLUSION_GAP_HOURS_MAX,
    COLLUSION_GAP_HOURS_MIN,
    COLLUSION_MERCHANT_COUNT,
    COLLUSION_MULTIPLIER_MAX,
    COLLUSION_MULTIPLIER_MIN,
    FRAUD_PATTERNS,
    GEO_GAP_MINUTES_MAX,
    GEO_GAP_MINUTES_MIN,
    GEO_MIN_DISTANCE_KM,
)
from streamguard.generator.reference_data import (
    CARD_TESTING_MCCS,
    FOREIGN_CITIES,
    HIGH_FRAUD_APPEAL_MCCS,
    MERCHANT_CATEGORIES,
)
from streamguard.generator.transactions import GenTransaction
from streamguard.utils.geo import haversine_km, jitter_coordinate
from streamguard.utils.logging_config import get_logger

log = get_logger(__name__)

CATEGORY_BY_MCC = {c.mcc: c for c in MERCHANT_CATEGORIES}


@dataclass
class FraudEpisode:
    """One compromised card and the transactions that resulted."""
    pattern: str
    card_ref: str
    customer_ref: str
    transactions: list[GenTransaction]


class FraudInjector:
    """Creates fraud episodes and merges them into normal activity."""

    def __init__(self, population: Population, seed: int, start: datetime):
        # Third independent random stream, distinct from population
        # (seed) and normal transactions (seed + 1_000_003).
        self.rng = np.random.default_rng(seed + 2_000_029)
        self.population = population
        self.start = start
        self._counter = 0

        self._build_indexes()

    def _build_indexes(self) -> None:
        merchants = self.population.merchants

        self.merchants = merchants
        self.merchant_refs = [m.merchant_ref for m in merchants]

        # Merchants fraudsters prefer: resellable, instantly consumable,
        # or hard to reverse.
        self.high_appeal_idx = [
            i for i, m in enumerate(merchants)
            if m.mcc in HIGH_FRAUD_APPEAL_MCCS
        ]
        # Low-value merchants suitable for a card-testing probe.
        self.testing_idx = [
            i for i, m in enumerate(merchants) if m.mcc in CARD_TESTING_MCCS
        ]
        self.online_idx = [i for i, m in enumerate(merchants) if m.is_online]

        # A fixed, small set of complicit merchants. Fixed because
        # collusion is a property of the MERCHANT, and the model must
        # be able to learn merchant-level aggregates.
        pool = self.high_appeal_idx or list(range(len(merchants)))
        chosen = self.rng.choice(
            pool, size=min(COLLUSION_MERCHANT_COUNT, len(pool)), replace=False
        )
        self.collusion_idx = [int(i) for i in chosen]

        self.customers_by_ref = {
            c.customer_ref: c for c in self.population.customers
        }
        self.cards_by_customer: dict[str, list] = {}
        for card in self.population.cards:
            if card.is_active:
                self.cards_by_customer.setdefault(
                    card.customer_ref, []
                ).append(card)

        self.eligible_customers = [
            c for c in self.population.customers
            if c.customer_ref in self.cards_by_customer
        ]

        # Devices the attacker controls, for account takeover: devices
        # NOT owned by the victim.
        self.foreign_devices = [
            d.device_ref for d in self.population.devices if d.is_personal
        ]
        # Devices grouped by their owner's customer_ref, so an episode
        # can pick a device the victim PLAUSIBLY already uses. Without
        # this, every fraud row looked like a brand-new device.
        self.devices_by_customer: dict[str, list[str]] = {}
        for d in self.population.devices:
            owner = getattr(d, "owner_ref", None) or getattr(d, "customer_ref", None)
            if owner:
                self.devices_by_customer.setdefault(owner, []).append(d.device_ref)

        self.all_devices = [d.device_ref for d in self.population.devices]

        log.info(
            "fraud_injector_ready",
            high_appeal_merchants=len(self.high_appeal_idx),
            testing_merchants=len(self.testing_idx),
            collusion_merchants=len(self.collusion_idx),
        )

    # ---------- Helpers ----------

    def _pick_device(self, customer, new_device_prob: float) -> str | None:
        """Choose a device for one fraud transaction.

        With probability new_device_prob the attacker's own device is
        used (unseen for this card). Otherwise one the customer already
        owns, so the transaction looks ordinary on that feature.

        Returning None is deliberately avoided: None was the original
        bug, because the feature engine reads a missing device as a
        brand-new one.
        """
        if float(self.rng.random()) < new_device_prob:
            pool = self.foreign_devices or self.all_devices
            if not pool:
                return None
            return str(pool[int(self.rng.integers(0, len(pool)))])

        owned = self.devices_by_customer.get(customer.customer_ref)
        if owned:
            return str(owned[int(self.rng.integers(0, len(owned)))])

        pool = self.all_devices
        if not pool:
            return None
        return str(pool[int(self.rng.integers(0, len(pool)))])
    def _next_ref(self) -> str:
        self._counter += 1
        return f"FRD{self._counter:09d}"

    def _pick_customer_and_card(self):
        customer = self.eligible_customers[
            int(self.rng.integers(0, len(self.eligible_customers)))
        ]
        cards = self.cards_by_customer[customer.customer_ref]
        card = cards[int(self.rng.integers(0, len(cards)))]
        return customer, card

    def _merchant_at(self, idx: int):
        return self.merchants[idx]

    def _pick_merchant(self, pool: list[int]) -> int:
        if not pool:
            pool = list(range(len(self.merchants)))
        return int(pool[int(self.rng.integers(0, len(pool)))])

    def _pick_merchant_near(self, customer, pool: list[int],
                            max_km: float, tries: int = 12) -> int:
        """Pick a merchant within max_km of the customer's home.

        WHY THIS EXISTS (Task 13.7C): normal transactions use distance
        decay, so a customer shops locally - median 2.3 km from home,
        99th percentile 21.7 km. Fraud used _pick_merchant, which draws
        uniformly across every city in the country. Result: even the
        10th percentile of account_takeover sat at 208 km, ten times
        normal's 99th. distance_from_home_km became a fraud marker
        carrying 46.84% of model gain - the generator telling the model
        the answer, exactly like the is_new_device bug.

        Rejection sampling rather than a precomputed index: this runs a
        few thousand times during generation, not per transaction, so
        simplicity beats speed here.
        """
        if not pool:
            pool = list(range(len(self.merchants)))

        for _ in range(tries):
            idx = int(pool[int(self.rng.integers(0, len(pool)))])
            m = self.merchants[idx]
            if haversine_km(customer.home_lat, customer.home_lon,
                            m.lat, m.lon) <= max_km:
                return idx

        # Nothing close enough found: fall back to the nearest in a
        # sample rather than giving up and picking at random.
        sample = [int(pool[int(self.rng.integers(0, len(pool)))])
                  for _ in range(min(40, len(pool)))]
        return min(sample, key=lambda i: haversine_km(
            customer.home_lat, customer.home_lon,
            self.merchants[i].lat, self.merchants[i].lon))

    def _build(
        self,
        customer,
        card,
        merchant_idx: int,
        occurred_at: datetime,
        amount: float,
        channel: Channel,
        entry_mode: EntryMode,
        fraud_type: FraudType,
        device_ref: str | None,
        lat: float | None = None,
        lon: float | None = None,
        city: str | None = None,
        country: str | None = None,
    ) -> GenTransaction:
        merchant = self._merchant_at(merchant_idx)

        if lat is None or lon is None:
            lat, lon = jitter_coordinate(merchant.lat, merchant.lon, 2.0, self.rng)

        return GenTransaction(
            transaction_ref=self._next_ref(),
            occurred_at=occurred_at,
            card_ref=card.card_ref,
            customer_ref=customer.customer_ref,
            merchant_ref=merchant.merchant_ref,
            device_ref=device_ref,
            amount=round(float(amount), 2),
            currency="INR" if (country or merchant.country) == "IN" else "USD",
            channel=channel.value,
            entry_mode=entry_mode.value,
            city=city or merchant.city,
            country=country or merchant.country,
            lat=round(float(lat), 6),
            lon=round(float(lon), 6),
            is_fraud=True,
            fraud_type=fraud_type.value,
        )

    # ---------- The five patterns ----------

    def _card_testing(self, anchor: datetime) -> FraudEpisode:
        """
        A stolen card number is probed with tiny charges, seconds apart,
        at low-friction online merchants. Signature: extreme velocity,
        trivial amounts.
        """
        customer, card = self._pick_customer_and_card()
        spec = next(p for p in FRAUD_PATTERNS if p.name == "card_testing")
        n = int(self.rng.integers(spec.min_txns, spec.max_txns + 1))

        pool = self.testing_idx or self.online_idx
        txns: list[GenTransaction] = []
        t = anchor

        # ONE device for the whole burst - the fraudster probes from
        # their own machine repeatedly. That reuse is itself a signal
        # the model must learn.
        burst_device = self._pick_device(customer, CARD_TESTING_NEW_DEVICE_PROB)

        # Jittered near home, not exactly ON it. Exact zero distance
        # was a label proxy.
        probe_lat, probe_lon = jitter_coordinate(
            customer.home_lat, customer.home_lon, CARD_TESTING_JITTER_KM, self.rng
        )

        for _ in range(n):
            amount = float(self.rng.uniform(
                CARD_TESTING_AMOUNT_MIN, CARD_TESTING_AMOUNT_MAX
            ))
            txns.append(self._build(
                customer, card, self._pick_merchant(pool), t, amount,
                Channel.ECOMMERCE, EntryMode.STORED_CREDENTIAL,
                FraudType.CARD_TESTING, device_ref=burst_device,
                lat=probe_lat, lon=probe_lon,
                city=customer.home_city, country=customer.home_country,
            ))
            t = t + timedelta(seconds=int(self.rng.integers(
                CARD_TESTING_GAP_SECONDS_MIN, CARD_TESTING_GAP_SECONDS_MAX
            )))

        return FraudEpisode("card_testing", card.card_ref,
                            customer.customer_ref, txns)

    def _account_takeover(self, anchor: datetime) -> FraudEpisode:
        """
        The attacker controls the account. Behaviour changes abruptly:
        a NEW device, categories the customer never uses, amounts far
        above their normal. Signature: deviation from personal baseline.
        """
        # Pick the MERCHANT first, then a customer who plausibly lives
        # near it. Collusion is a property of the merchant, and a real
        # complicit shop serves local customers - picking them at
        # random across the country made distance a fraud marker.


        customer, card = self._pick_customer_and_card()
        spec = next(p for p in FRAUD_PATTERNS if p.name == "account_takeover")
        n = int(self.rng.integers(spec.min_txns, spec.max_txns + 1))

        # 80% a device the victim has never used - this is the one
        # pattern where "new device" is genuinely the signal. The other
        # 20% models an attacker on a device already linked to the
        # account, which a real system must also catch.
        attacker_device = self._pick_device(customer, ATO_NEW_DEVICE_PROB)

        pool = self.high_appeal_idx
        txns: list[GenTransaction] = []
        t = anchor

        for _ in range(n):
            multiplier = float(self.rng.uniform(
                ATO_AMOUNT_MULTIPLIER_MIN, ATO_AMOUNT_MULTIPLIER_MAX
            ))
            amount = customer.typical_txn_amount * multiplier

            txns.append(self._build(
                customer, card,
                self._pick_merchant_near(customer, pool, ATO_MERCHANT_MAX_KM),
                t, amount,
                Channel.ECOMMERCE, EntryMode.STORED_CREDENTIAL,
                FraudType.ACCOUNT_TAKEOVER, device_ref=attacker_device,
            ))
            t = t + timedelta(minutes=int(self.rng.integers(
                ATO_GAP_MINUTES_MIN, ATO_GAP_MINUTES_MAX
            )))

        return FraudEpisode("account_takeover", card.card_ref,
                            customer.customer_ref, txns)

    def _geo_impossible(self, anchor: datetime) -> FraudEpisode:
        """
        A legitimate-looking transaction at home, then the same card
        used hundreds of kilometres away minutes later. Signature:
        implied travel speed far beyond any aircraft.

        NOTE: the first transaction is labelled fraud too. In reality
        the home transaction may be genuine, but the pair is what
        constitutes the signal, and labelling both keeps the episode
        coherent. This is an assumption worth stating in the report.
        """
        customer, card = self._pick_customer_and_card()
        txns: list[GenTransaction] = []

        # A cloned physical card: the device is largely irrelevant, so
        # it should look like normal traffic rather than flag itself.
        episode_device = self._pick_device(customer, GEO_NEW_DEVICE_PROB)

        # Mostly POS, but not exclusively - all-POS pinned
        # is_card_present to 1.0 and is_ecommerce to 0.0.
        if float(self.rng.random()) < GEO_POS_SHARE:
            home_channel, home_entry = Channel.POS, EntryMode.CHIP
        else:
            home_channel, home_entry = Channel.ECOMMERCE, EntryMode.STORED_CREDENTIAL

        # 1. Near home, physical card present
        home_idx = self._pick_merchant(list(range(len(self.merchants))))
        txns.append(self._build(
            customer, card, home_idx, anchor,
            customer.typical_txn_amount * float(self.rng.uniform(0.6, 2.2)),
            home_channel, home_entry, FraudType.GEO_IMPOSSIBLE,
            device_ref=episode_device,
            lat=customer.home_lat, lon=customer.home_lon,
            city=customer.home_city, country=customer.home_country,
        ))

        # 2. Far away, far too soon
        far_city = FOREIGN_CITIES[int(self.rng.integers(0, len(FOREIGN_CITIES)))]
        distance = haversine_km(
            customer.home_lat, customer.home_lon, far_city.lat, far_city.lon
        )
        # Guard: if the chosen city is somehow close, the signal is weak
        if distance < GEO_MIN_DISTANCE_KM:
            far_city = FOREIGN_CITIES[0]

        n_far = int(self.rng.integers(1, 4))
        t = anchor
        for _ in range(n_far):
            t = t + timedelta(minutes=int(self.rng.integers(
                GEO_GAP_MINUTES_MIN, GEO_GAP_MINUTES_MAX
            )))
            lat, lon = jitter_coordinate(far_city.lat, far_city.lon, 8.0, self.rng)
            if float(self.rng.random()) < GEO_POS_SHARE:
                far_channel, far_entry = Channel.POS, EntryMode.SWIPE
            else:
                far_channel, far_entry = Channel.ECOMMERCE, EntryMode.MANUAL
            txns.append(self._build(
                customer, card, self._pick_merchant(self.high_appeal_idx), t,
                customer.typical_txn_amount * float(self.rng.uniform(2.0, 11.0)),
                far_channel, far_entry, FraudType.GEO_IMPOSSIBLE,
                device_ref=episode_device,
                lat=lat, lon=lon,
                city=far_city.name, country=far_city.country,
            ))

        return FraudEpisode("geo_impossible", card.card_ref,
                            customer.customer_ref, txns)

    def _merchant_collusion(self, anchor: datetime) -> FraudEpisode:
        """
        A complicit merchant inflates amounts on genuine cards. The
        cardholder behaves normally; the MERCHANT is the anomaly.
        Signature: merchant-level aggregates, not per-transaction oddity.

        This is the hardest pattern to detect per-transaction, and that
        is the point - it forces merchant aggregate features in Task 10.
        """
        # Pick the MERCHANT first, then a customer who plausibly lives
        # near it. Collusion is a property of the merchant, and a real
        # complicit shop serves local customers.
        #
        # BUG FIXED (Task 13.7C): the old order picked a customer at
        # random anywhere in the country, so distance_from_home_km had
        # a median of 973 km against normal traffic's 2.3 km.
        merchant_idx = self.collusion_idx[
            int(self.rng.integers(0, len(self.collusion_idx)))
        ]
        merchant = self._merchant_at(merchant_idx)
        category = CATEGORY_BY_MCC[merchant.mcc]

        customer, card = self._pick_customer_and_card()
        for _ in range(25):
            if haversine_km(customer.home_lat, customer.home_lon,
                            merchant.lat, merchant.lon) <= COLLUSION_MERCHANT_MAX_KM:
                break
            customer, card = self._pick_customer_and_card()

        spec = next(p for p in FRAUD_PATTERNS if p.name == "merchant_collusion")
        n = int(self.rng.integers(spec.min_txns, spec.max_txns + 1))

        txns: list[GenTransaction] = []
        t = anchor

        # The CUSTOMER is genuine here and so is their device - the
        # merchant is the anomaly. Should look like normal traffic.
        episode_device = self._pick_device(customer, COLLUSION_NEW_DEVICE_PROB)

        for _ in range(n):
            multiplier = float(self.rng.uniform(
                COLLUSION_MULTIPLIER_MIN, COLLUSION_MULTIPLIER_MAX
            ))
            amount = min(
                category.median_amount * multiplier, category.max_amount
            )

            # Mostly a physical swipe, but not exclusively - all-POS
            # pinned is_card_present to 1.0 across every collusion row.
            # Channel and entry mode come from ONE draw so they stay
            # consistent with each other.
            if float(self.rng.random()) < COLLUSION_POS_SHARE:
                channel, entry_mode = Channel.POS, EntryMode.CHIP
            else:
                channel, entry_mode = Channel.ECOMMERCE, EntryMode.STORED_CREDENTIAL

            txns.append(self._build(
                customer, card, merchant_idx, t, amount,
                channel, entry_mode, FraudType.MERCHANT_COLLUSION,
                device_ref=episode_device,
            ))
            t = t + timedelta(hours=int(self.rng.integers(
                COLLUSION_GAP_HOURS_MIN, COLLUSION_GAP_HOURS_MAX
            )))

        return FraudEpisode("merchant_collusion", card.card_ref,
                            customer.customer_ref, txns)
        spec = next(p for p in FRAUD_PATTERNS if p.name == "merchant_collusion")
        n = int(self.rng.integers(spec.min_txns, spec.max_txns + 1))

        # A device the victim has never used before
        # 80% a device the victim has never used - this is the one
        # pattern where "new device" is genuinely the signal. The other
        # 20% models an attacker on a device already linked to the
        # account, which a real system must also catch.
        attacker_device = self._pick_device(customer, ATO_NEW_DEVICE_PROB)

        pool = self.high_appeal_idx
        txns: list[GenTransaction] = []
        t = anchor

        for _ in range(n):
            multiplier = float(self.rng.uniform(
                ATO_AMOUNT_MULTIPLIER_MIN, ATO_AMOUNT_MULTIPLIER_MAX
            ))
            amount = customer.typical_txn_amount * multiplier

            txns.append(self._build(
                customer, card, self._pick_merchant(pool), t, amount,
                Channel.ECOMMERCE, EntryMode.STORED_CREDENTIAL,
                FraudType.ACCOUNT_TAKEOVER, device_ref=attacker_device,
            ))
            t = t + timedelta(minutes=int(self.rng.integers(
                ATO_GAP_MINUTES_MIN, ATO_GAP_MINUTES_MAX
            )))

        return FraudEpisode("account_takeover", card.card_ref,
                            customer.customer_ref, txns)

   
    def _card_not_present(self, anchor: datetime) -> FraudEpisode:
        """
        Stolen card details used online at high-value merchants. No
        physical card, no customer device. Signature: channel +
        category + amount combination.
        """
        customer, card = self._pick_customer_and_card()
        spec = next(p for p in FRAUD_PATTERNS if p.name == "card_not_present")
        n = int(self.rng.integers(spec.min_txns, spec.max_txns + 1))

        pool = [i for i in self.high_appeal_idx if self.merchants[i].is_online]
        if not pool:
            pool = self.high_appeal_idx

        txns: list[GenTransaction] = []
        t = anchor

        episode_device = self._pick_device(customer, CNP_NEW_DEVICE_PROB)

        for _ in range(n):
            multiplier = float(self.rng.uniform(
                CNP_AMOUNT_MULTIPLIER_MIN, CNP_AMOUNT_MULTIPLIER_MAX
            ))
            amount = customer.typical_txn_amount * multiplier

            # ONLINE purchase: the customer does not physically move,
            # so use THEIR location, not the merchant's. The old code
            # used merchant coordinates scattered nationwide, which
            # produced phantom implied speeds averaging 1,384 km/h.
            buyer_lat, buyer_lon = jitter_coordinate(
                customer.home_lat, customer.home_lon, 3.0, self.rng
            )
            txns.append(self._build(
                customer, card, self._pick_merchant(pool), t, amount,
                Channel.ECOMMERCE, EntryMode.MANUAL,
                FraudType.CARD_NOT_PRESENT, device_ref=episode_device,
                lat=buyer_lat, lon=buyer_lon,
                city=customer.home_city, country=customer.home_country,
            ))
            # BUG FIXED (Task 13.7C): this line was lost in an earlier
            # edit, so every transaction in a CNP episode shared one
            # timestamp. seconds_since_prev came out 0, and distance
            # divided by zero hit the 99,999 speed sentinel on 62.6%
            # of CNP rows. Silent - nothing errored.
            t = t + timedelta(minutes=int(self.rng.integers(
                CNP_GAP_MINUTES_MIN, CNP_GAP_MINUTES_MAX
            )))

        return FraudEpisode("card_not_present", card.card_ref,
                            customer.customer_ref, txns)

    # ---------- Orchestration ----------

    def generate_episodes(
        self, target_fraud_txns: int, n_days: int
    ) -> list[FraudEpisode]:
        """
        Generate episodes until roughly target_fraud_txns rows exist.

        We target a TRANSACTION count, not an episode count, because the
        fraud rate is defined over transactions. Episode sizes vary, so
        we generate until we reach the target.
        """
        builders = {
            "card_testing": self._card_testing,
            "account_takeover": self._account_takeover,
            "geo_impossible": self._geo_impossible,
            "merchant_collusion": self._merchant_collusion,
            "card_not_present": self._card_not_present,
        }

        names = [p.name for p in FRAUD_PATTERNS]
        shares = [p.share for p in FRAUD_PATTERNS]

        episodes: list[FraudEpisode] = []
        produced = 0
        guard = 0

        while produced < target_fraud_txns and guard < target_fraud_txns * 10:
            guard += 1
            pattern = str(self.rng.choice(names, p=shares))
            anchor = self._random_anchor(n_days)
            episode = builders[pattern](anchor)
            episodes.append(episode)
            produced += len(episode.transactions)

        log.info(
            "fraud_episodes_generated",
            episodes=len(episodes),
            transactions=produced,
            target=target_fraud_txns,
        )
        return episodes

    def _random_anchor(self, n_days: int) -> datetime:
        """A random moment within the ACTUAL simulation window."""
        day = int(self.rng.integers(0, max(n_days, 1)))
        hour = int(self.rng.integers(0, 24))
        minute = int(self.rng.integers(0, 60))
        second = int(self.rng.integers(0, 60))

        return (self.start + timedelta(days=day)).replace(
            hour=hour, minute=minute, second=second
        )