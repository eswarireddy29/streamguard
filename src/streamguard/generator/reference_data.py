"""
Fixed reference data for the synthetic world.

Cities, merchant categories, device types and card types. These are
constants, not generated — they define the universe in which
customers, merchants and transactions are created.

Coordinates are approximate city centres. Amount ranges are
plausible values in Indian rupees, chosen to make categories
distinguishable; they are illustrative, not survey data.
"""

from __future__ import annotations

from dataclasses import dataclass


# ============================================================
#  Cities
# ============================================================

@dataclass(frozen=True)
class City:
    name: str
    country: str          # ISO 3166-1 alpha-2
    lat: float
    lon: float
    weight: float         # relative likelihood of a customer living here
    is_domestic: bool = True


DOMESTIC_CITIES: list[City] = [
    City("Mumbai",         "IN", 19.0760, 72.8777, 21.0),
    City("Delhi",          "IN", 28.6139, 77.2090, 19.0),
    City("Bangalore",      "IN", 12.9716, 77.5946, 13.0),
    City("Hyderabad",      "IN", 17.3850, 78.4867, 10.0),
    City("Chennai",        "IN", 13.0827, 80.2707,  9.0),
    City("Kolkata",        "IN", 22.5726, 88.3639,  9.0),
    City("Pune",           "IN", 18.5204, 73.8567,  7.0),
    City("Ahmedabad",      "IN", 23.0225, 72.5714,  6.5),
    City("Surat",          "IN", 21.1702, 72.8311,  5.0),
    City("Jaipur",         "IN", 26.9124, 75.7873,  4.5),
    City("Lucknow",        "IN", 26.8467, 80.9462,  4.0),
    City("Nagpur",         "IN", 21.1458, 79.0882,  3.5),
    City("Indore",         "IN", 22.7196, 75.8577,  3.2),
    City("Bhopal",         "IN", 23.2599, 77.4126,  2.8),
    City("Visakhapatnam",  "IN", 17.6868, 83.2185,  2.6),
    City("Coimbatore",     "IN", 11.0168, 76.9558,  2.5),
    City("Kochi",          "IN",  9.9312, 76.2673,  2.3),
    City("Chandigarh",     "IN", 30.7333, 76.7794,  2.0),
    City("Guwahati",       "IN", 26.1445, 91.7362,  1.8),
    City("Tirupati",       "IN", 13.6288, 79.4192,  1.5),
]

# Used only for geo-impossible fraud and genuine foreign travel.
# No customer is assigned a foreign home city.
FOREIGN_CITIES: list[City] = [
    City("Dubai",     "AE", 25.2048, 55.2708, 1.0, is_domestic=False),
    City("Singapore", "SG",  1.3521, 103.8198, 1.0, is_domestic=False),
    City("London",    "GB", 51.5074,  -0.1278, 1.0, is_domestic=False),
    City("New York",  "US", 40.7128, -74.0060, 1.0, is_domestic=False),
    City("Bangkok",   "TH", 13.7563, 100.5018, 1.0, is_domestic=False),
    City("Hong Kong", "HK", 22.3193, 114.1694, 1.0, is_domestic=False),
]

ALL_CITIES: list[City] = DOMESTIC_CITIES + FOREIGN_CITIES


# ============================================================
#  Merchant categories
# ============================================================

@dataclass(frozen=True)
class MerchantCategory:
    """
    A type of business.

    mcc           : Merchant Category Code — the real four-digit industry
                    standard that payment networks use to classify businesses.
    median_amount : typical spend, in rupees
    sigma         : spread of the lognormal amount distribution.
                    Higher = more variable spending in this category.
    base_risk     : baseline fraud propensity, 0..1. Ground truth used by
                    the generator; the model must LEARN this, never see it.
    online_share  : probability a transaction here is e-commerce
    recurring     : whether this category produces subscription payments
    """
    mcc: str
    name: str
    median_amount: float
    sigma: float
    min_amount: float
    max_amount: float
    base_risk: float
    online_share: float
    recurring: bool = False


MERCHANT_CATEGORIES: list[MerchantCategory] = [
    # --- Everyday, low risk ---
    MerchantCategory("5411", "Grocery & Supermarket",  850,  0.70,   50,   15000, 0.04, 0.15),
    MerchantCategory("5814", "Fast Food",              260,  0.55,   40,    3000, 0.05, 0.35),
    MerchantCategory("5812", "Restaurant",             900,  0.75,   80,   12000, 0.06, 0.25),
    MerchantCategory("5541", "Fuel Station",          1600,  0.50,  200,    8000, 0.08, 0.02),
    MerchantCategory("5912", "Pharmacy",               420,  0.80,   30,    8000, 0.05, 0.20),
    MerchantCategory("4111", "Public Transport",        90,  0.60,   10,    1500, 0.03, 0.55),
    MerchantCategory("4121", "Taxi & Rideshare",       280,  0.70,   40,    4000, 0.07, 0.90),

    # --- Retail, moderate risk ---
    MerchantCategory("5651", "Clothing & Apparel",    1800,  0.90,  200,   40000, 0.12, 0.55),
    MerchantCategory("5310", "Discount Store",         950,  0.80,   80,   20000, 0.08, 0.30),
    MerchantCategory("5942", "Books & Stationery",     480,  0.75,   50,    6000, 0.06, 0.45),
    MerchantCategory("5999", "Miscellaneous Retail",  1100,  0.95,   60,   30000, 0.11, 0.40),
    MerchantCategory("7832", "Cinema & Entertainment", 520,  0.60,   80,    5000, 0.07, 0.60),

    # --- High value, higher risk ---
    MerchantCategory("5732", "Electronics",           8500,  1.10,  500,  180000, 0.22, 0.60),
    MerchantCategory("7011", "Hotel & Lodging",       5200,  0.95,  600,   90000, 0.18, 0.70),
    MerchantCategory("4511", "Airline",               9800,  0.85, 1500,  150000, 0.20, 0.95),
    MerchantCategory("5944", "Jewellery",            32000,  1.20, 2000,  500000, 0.30, 0.30),

    # --- Elevated risk categories ---
    MerchantCategory("5967", "Direct Marketing",      2400,  1.15,  100,   60000, 0.38, 1.00),
    MerchantCategory("7995", "Gaming & Betting",      1500,  1.30,  100,   80000, 0.45, 1.00),
    MerchantCategory("6051", "Crypto & Money Transfer", 7000, 1.25,  500,  250000, 0.42, 1.00),

    # --- Recurring / subscription ---
    MerchantCategory("4899", "Streaming & Cable",      399,  0.35,   99,    2000, 0.04, 1.00, recurring=True),
    MerchantCategory("4814", "Telecom",                599,  0.45,  149,    5000, 0.05, 0.80, recurring=True),
    MerchantCategory("8062", "Hospital & Clinic",     3200,  1.05,  200,  120000, 0.07, 0.15),
]

# Categories a fraudster prefers: easy to resell, instantly consumable,
# or hard to reverse. Used by the fraud injector in Task 7.
HIGH_FRAUD_APPEAL_MCCS: set[str] = {
    "5732", "5944", "6051", "7995", "5967", "4511", "7011",
}

# Categories plausible for a tiny "card testing" probe — a fraudster
# checking whether a stolen card still works with a small purchase.
CARD_TESTING_MCCS: set[str] = {"4899", "5814", "4111", "5942", "5912"}


# ============================================================
#  Devices and cards
# ============================================================

@dataclass(frozen=True)
class DeviceType:
    name: str
    os_family: str
    weight: float
    is_personal: bool   # personal devices stay with one customer


DEVICE_TYPES: list[DeviceType] = [
    DeviceType("android_phone", "Android", 44.0, True),
    DeviceType("ios_phone",     "iOS",     18.0, True),
    DeviceType("windows_pc",    "Windows", 12.0, True),
    DeviceType("mac_pc",        "macOS",    4.0, True),
    DeviceType("pos_terminal",  "Embedded", 16.0, False),
    DeviceType("atm",           "Embedded",  6.0, False),
]

CARD_TYPES: list[tuple[str, float, float, float]] = [
    # (type, weight, min credit limit, max credit limit)
    ("debit",   58.0,  25_000,   300_000),
    ("credit",  36.0,  50_000, 1_000_000),
    ("prepaid",  6.0,   5_000,    50_000),
]

RISK_BANDS: list[tuple[str, float]] = [
    ("low",    0.70),
    ("medium", 0.24),
    ("high",   0.06),
]