"""
Behavioural patterns that shape normal transaction activity.

Three questions this module answers:
  WHEN  does a transaction happen (hour of day, day of week)?
  HOW MUCH is it for?
  WHERE does it happen relative to the customer's home?

Fraud detection works by measuring deviation from a baseline. If the
baseline is random noise, nothing can deviate from it and no model can
learn. So these patterns must be genuinely structured.
"""

from __future__ import annotations

import numpy as np

from streamguard.generator.reference_data import MerchantCategory

# ============================================================
#  Hour-of-day profiles
# ============================================================
# 24 weights, one per hour, starting at midnight. Relative, not
# probabilities -- they get normalised before use.
#
# Shape: dead at night, a morning rise, a lunch spike around 13:00,
# a dip in the afternoon, an evening peak around 19:00-21:00.

BASE_HOURLY_WEIGHTS = np.array([
    0.8,  0.4,  0.3,  0.2,  0.2,  0.4,   # 00-05  night
    1.2,  2.4,  3.8,  4.6,  4.9,  5.4,   # 06-11  morning
    6.8,  7.6,  6.2,  5.1,  5.3,  6.0,   # 12-17  lunch peak, afternoon
    7.4,  8.2,  7.1,  5.2,  3.1,  1.6,   # 18-23  evening peak
])

# Some categories have their own rhythm that overrides the general shape.
CATEGORY_HOUR_OVERRIDES: dict[str, np.ndarray] = {
    # Fast food -- sharp lunch and dinner spikes
    "5814": np.array([
        0.5, 0.3, 0.2, 0.2, 0.2, 0.5,
        1.5, 2.8, 3.2, 2.6, 3.4, 6.5,
        9.5, 8.0, 4.2, 3.4, 4.0, 6.2,
        8.8, 8.4, 5.6, 3.0, 1.6, 0.9,
    ]),
    # Public transport -- commuter double peak
    "4111": np.array([
        0.2, 0.1, 0.1, 0.1, 0.3, 1.8,
        5.2, 9.4, 10.5, 6.1, 3.2, 2.6,
        3.0, 2.8, 2.6, 3.1, 5.4, 9.8,
        9.2, 5.0, 2.4, 1.2, 0.6, 0.3,
    ]),
    # Fuel -- morning and evening commute
    "5541": np.array([
        0.4, 0.2, 0.2, 0.2, 0.4, 1.6,
        4.2, 6.8, 7.4, 5.2, 4.0, 3.8,
        4.2, 4.0, 3.8, 4.2, 5.6, 7.8,
        7.2, 5.4, 3.2, 1.8, 0.9, 0.5,
    ]),
    # Cinema -- evenings and late shows
    "7832": np.array([
        0.3, 0.2, 0.1, 0.1, 0.1, 0.2,
        0.4, 0.8, 1.2, 1.8, 2.6, 3.4,
        4.2, 4.8, 4.4, 4.0, 4.6, 6.2,
        8.4, 9.6, 8.8, 6.4, 3.2, 1.2,
    ]),
    # Gaming & betting -- genuinely nocturnal
    "7995": np.array([
        3.2, 2.6, 1.8, 1.2, 0.8, 0.6,
        0.8, 1.2, 1.8, 2.4, 2.8, 3.2,
        3.6, 3.8, 3.6, 3.8, 4.2, 5.0,
        6.2, 7.4, 8.2, 8.0, 6.4, 4.6,
    ]),
}

# ============================================================
#  Day-of-week multipliers  (Monday = 0 ... Sunday = 6)
# ============================================================

BASE_DOW_WEIGHTS = np.array([0.95, 0.92, 0.94, 1.00, 1.18, 1.35, 1.12])

CATEGORY_DOW_OVERRIDES: dict[str, np.ndarray] = {
    "4111": np.array([1.30, 1.28, 1.30, 1.26, 1.20, 0.45, 0.30]),  # transport
    "7832": np.array([0.55, 0.50, 0.60, 0.75, 1.45, 2.10, 1.70]),  # cinema
    "5812": np.array([0.70, 0.68, 0.78, 0.95, 1.45, 1.85, 1.45]),  # restaurant
    "5411": np.array([0.85, 0.82, 0.88, 0.95, 1.20, 1.55, 1.30]),  # grocery
    "8062": np.array([1.25, 1.22, 1.20, 1.18, 1.10, 0.55, 0.30]),  # clinic
}


# ============================================================
#  Timing
# ============================================================

def hourly_profile(mcc: str, night_owl: float) -> np.ndarray:
    """
    Probability of each hour of the day for a given category and person.

    Args:
        mcc: merchant category code
        night_owl: 0..1, how much this customer shifts activity to
                   late hours. A value of 0 leaves the profile
                   untouched; 1 substantially boosts 22:00-04:00.

    Returns:
        24 probabilities summing to 1.
    """
    weights = CATEGORY_HOUR_OVERRIDES.get(mcc, BASE_HOURLY_WEIGHTS).astype(float).copy()

    if night_owl > 0:
        # Boost 22:00-04:00 in proportion to the trait
        night_hours = [22, 23, 0, 1, 2, 3, 4]
        boost = 1.0 + night_owl * 4.0
        for h in night_hours:
            weights[h] *= boost

    return weights / weights.sum()


def dow_multiplier(mcc: str, weekday: int) -> float:
    """Relative activity level for this category on this weekday."""
    weights = CATEGORY_DOW_OVERRIDES.get(mcc, BASE_DOW_WEIGHTS)
    return float(weights[weekday])


def sample_hour(rng: np.random.Generator, mcc: str, night_owl: float) -> int:
    """Pick an hour of day from the appropriate profile."""
    return int(rng.choice(24, p=hourly_profile(mcc, night_owl)))


def sample_second_within_hour(rng: np.random.Generator) -> tuple[int, int]:
    """Minute and second, uniform within the hour."""
    return int(rng.integers(0, 60)), int(rng.integers(0, 60))


# ============================================================
#  Amounts
# ============================================================

def sample_amount(
    rng: np.random.Generator,
    category: MerchantCategory,
    customer_typical: float,
    customer_scale_bias: float = 1.0,
) -> float:
    """
    Draw a transaction amount.

    Blends two things: what this CATEGORY typically costs, and what
    this CUSTOMER typically spends. A wealthy customer at a grocery
    store still spends grocery-store money, just somewhat more.

    The blend is deliberate. Using only the category would make every
    customer identical; using only the customer would erase category
    structure. Both signals must survive for the model to learn either.
    """
    # Ratio of this customer's typical spend to the population median (~1000)
    customer_factor = float(np.clip(customer_typical / 1000.0, 0.35, 4.0))

    # Geometric blend: 70% category, 30% customer
    effective_median = (
        (category.median_amount ** 0.70)
        * ((category.median_amount * customer_factor) ** 0.30)
        * customer_scale_bias
    )

    value = rng.lognormal(mean=np.log(effective_median), sigma=category.sigma)
    value = float(np.clip(value, category.min_amount, category.max_amount))

    return _round_like_a_human(rng, value)


def _round_like_a_human(rng: np.random.Generator, amount: float) -> float:
    """
    Real payment amounts are not uniformly distributed to the paisa.

    Prices cluster on round numbers and on .99 endings. Without this,
    every amount would have a random decimal and the data would look
    obviously synthetic to anyone who looked at it closely.
    """
    draw = rng.random()

    if draw < 0.30:                      # round to nearest 10
        return float(round(amount / 10) * 10) or 10.0
    if draw < 0.45:                      # round to nearest 50
        return float(round(amount / 50) * 50) or 50.0
    if draw < 0.58:                      # .99 ending
        return float(int(amount)) - 0.01 if amount > 1 else 0.99
    if draw < 0.72:                      # whole rupees
        return float(int(amount)) or 1.0
    return round(amount, 2)              # exact


# ============================================================
#  Location
# ============================================================

def choose_location_mode(
    rng: np.random.Generator, travel_propensity: float
) -> str:
    """
    Decide where this transaction happens.

    Returns one of:
        "home"     -- near the customer's home city (the common case)
        "nearby"   -- same city, further out
        "domestic" -- a different Indian city (travel)
        "foreign"  -- abroad (rare, legitimate travel)
    """
    travel_chance = travel_propensity
    draw = rng.random()

    if draw < 1.0 - travel_chance - 0.08:
        return "home"
    if draw < 1.0 - travel_chance:
        return "nearby"
    if draw < 1.0 - travel_chance * 0.12:
        return "domestic"
    return "foreign"


# ============================================================
#  Merchant selection
# ============================================================

def merchant_selection_weights(
    category_affinity: dict[str, float],
    merchant_mccs: np.ndarray,
    distances_km: np.ndarray,
    online_flags: np.ndarray,
    online_preference: float,
) -> np.ndarray:
    """
    Score every merchant for how likely this customer is to use it.

    Three factors multiply together:
      1. category affinity -- does this customer shop in this category?
      2. distance decay    -- physical shops close to home are preferred
      3. online preference -- some customers shop online more

    Returns weights summing to 1.
    """
    affinity = np.array(
        [category_affinity.get(mcc, 0.001) for mcc in merchant_mccs],
        dtype=float,
    )

    # Distance decay with a 25 km half-life. Online merchants are
    # exempt -- distance is irrelevant to an e-commerce purchase.
    decay = np.exp(-distances_km / 25.0)
    decay = np.where(online_flags, 1.0, decay)

    # Nudge toward or away from online merchants
    online_factor = np.where(
        online_flags,
        0.4 + online_preference * 1.6,
        1.4 - online_preference * 0.8,
    )

    weights = affinity * decay * online_factor
    total = weights.sum()

    if total <= 0:
        return np.full(len(merchant_mccs), 1.0 / len(merchant_mccs))

    return weights / total