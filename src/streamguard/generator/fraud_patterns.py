"""
Fraud pattern definitions.

Five patterns, each with a DIFFERENT signature. This matters: a single
pattern would let a model memorise one rule and score brilliantly
while learning nothing. Five distinct signatures force it to learn
genuinely different signals, and give honest per-pattern recall in
Task 15.

IMPORTANT HONESTY NOTE: these patterns encode MY assumptions about how
fraud behaves. A model that catches them has learned my patterns, not
real-world fraud. This belongs in the README and the report, stated
plainly.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FraudPatternSpec:
    """
    Configuration for one fraud pattern.

    share : fraction of all fraud this pattern accounts for.
            The five shares must sum to 1.0.
    """
    name: str
    share: float
    min_txns: int          # transactions per fraud episode
    max_txns: int
    description: str


# Shares roughly reflect reported industry mixes: card-not-present
# dominates, card testing is common, collusion is rarer. They are
# illustrative, not survey data.
FRAUD_PATTERNS: list[FraudPatternSpec] = [
    FraudPatternSpec(
        name="card_not_present",
        share=0.34,
        min_txns=1,
        max_txns=4,
        description="Stolen card details used online at high-value merchants",
    ),
    FraudPatternSpec(
        name="card_testing",
        share=0.24,
        min_txns=6,
        max_txns=22,
        description="Rapid burst of tiny charges to check if a card is live",
    ),
    FraudPatternSpec(
        name="account_takeover",
        share=0.22,
        min_txns=3,
        max_txns=11,
        description="Attacker controls the account; behaviour changes abruptly",
    ),
    FraudPatternSpec(
        name="geo_impossible",
        share=0.12,
        min_txns=2,
        max_txns=5,
        description="Same card in two places too far apart, too fast",
    ),
    FraudPatternSpec(
        name="merchant_collusion",
        share=0.08,
        min_txns=2,
        max_txns=6,
        description="Complicit merchant inflating amounts on genuine cards",
    ),
]


# ============================================================
#  Pattern-specific parameters
# ============================================================

# --- Card testing ---
# Tiny amounts, seconds apart, usually at low-friction online merchants.
CARD_TESTING_AMOUNT_MIN = 1.0
CARD_TESTING_AMOUNT_MAX = 99.0
CARD_TESTING_GAP_SECONDS_MIN = 8
CARD_TESTING_GAP_SECONDS_MAX = 240

# --- Account takeover ---
# Amounts jump well above the customer's normal, categories shift to
# resellable goods, and a NEW device appears.
ATO_AMOUNT_MULTIPLIER_MIN = 3.5
ATO_AMOUNT_MULTIPLIER_MAX = 14.0
ATO_GAP_MINUTES_MIN = 12
ATO_GAP_MINUTES_MAX = 400

# --- Geo-impossible ---
# The second transaction lands far away, far too soon.
GEO_GAP_MINUTES_MIN = 6
GEO_GAP_MINUTES_MAX = 95
GEO_MIN_DISTANCE_KM = 900.0

# --- Merchant collusion ---
# Amounts inflated 2-6x at one specific merchant.
COLLUSION_MULTIPLIER_MIN = 2.2
COLLUSION_MULTIPLIER_MAX = 6.5
COLLUSION_MERCHANT_COUNT = 6      # how many merchants are complicit
COLLUSION_GAP_HOURS_MIN = 2
COLLUSION_GAP_HOURS_MAX = 72

# --- Card not present ---
# Online, high-value, stored-credential, no physical card.
CNP_AMOUNT_MULTIPLIER_MIN = 2.0
CNP_AMOUNT_MULTIPLIER_MAX = 9.0
CNP_GAP_MINUTES_MIN = 3
CNP_GAP_MINUTES_MAX = 180

# --- Fraud merchant locality  (Task 13.7C fix) ---------------------
# Normal traffic: median 2.3 km from home, p99 21.7 km (distance decay
# in transactions.py). Fraud used uniform random merchant selection
# across the whole country, so distance_from_home_km separated fraud
# from normal by construction.
#
# account_takeover: the attacker shops where the victim would not, so
# SOME distance increase is realistic - but tens of km, not hundreds.
ATO_MERCHANT_MAX_KM = 60.0

# merchant_collusion: the CUSTOMER is genuine and shops locally. Only
# the merchant is dishonest. Should look like normal traffic.
COLLUSION_MERCHANT_MAX_KM = 25.0

# ============================================================
#  Device and channel realism  (Task 13.7 fix)
# ============================================================
# BUG FIXED: four of five patterns passed device_ref=None, which the
# feature engine read as "a device this card has never used". Result:
# is_new_device = 1.0000 on every row of those four patterns vs 0.079
# for normal traffic - a label proxy carrying 58.65% of model gain.
#
# A fraud pattern must SHIFT a feature's distribution, never pin it to
# a constant. These are per-EPISODE probabilities that the attacker
# uses a device the card has not been seen with.

# card_testing: the CARD NUMBER is stolen, not the phone. The fraudster
# probes from their own machine, reusing it across the burst.
CARD_TESTING_NEW_DEVICE_PROB = 0.25

# card_not_present: stolen details used online. Could be any device.
CNP_NEW_DEVICE_PROB = 0.45

# geo_impossible: a physically cloned card swiped at a terminal. The
# device is largely irrelevant, so it should look like normal traffic.
GEO_NEW_DEVICE_PROB = 0.10

# merchant_collusion: the CUSTOMER is genuine and so is their device.
# The merchant is the anomaly.
COLLUSION_NEW_DEVICE_PROB = 0.08

# account_takeover: the attacker controls the account from their OWN
# device. The one pattern where a new device is genuinely the signal.
ATO_NEW_DEVICE_PROB = 0.80

# --- Channel mixes -------------------------------------------------
# geo_impossible and merchant_collusion previously used Channel.POS
# exclusively, pinning is_card_present to 1.0 and is_ecommerce to 0.0.
# A minority of the other channel turns a constant into a shift.
GEO_POS_SHARE = 0.85
COLLUSION_POS_SHARE = 0.88

# --- Card testing location -----------------------------------------
# BUG FIXED: card_testing used the customer's exact home coordinates
# with no jitter, so distance_from_home_km was exactly 0.0000 on all
# 1,165 rows (normal traffic has 539,907 distinct values).
CARD_TESTING_JITTER_KM = 4.0


def validate_shares() -> None:
    """Fail fast if the pattern shares do not sum to 1."""
    total = sum(p.share for p in FRAUD_PATTERNS)
    if abs(total - 1.0) > 1e-6:
        raise ValueError(
            f"Fraud pattern shares must sum to 1.0, got {total:.6f}"
        )


validate_shares()