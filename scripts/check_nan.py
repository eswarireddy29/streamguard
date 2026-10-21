"""Does the schema reject NaN?"""

from streamguard.api.schemas import ScoreRequest

BASE = {
    "transaction_ref": "T1",
    "occurred_at": "2026-03-20T14:30:00+05:30",
    "card_ref": "C1",
    "customer_ref": "CU1",
    "merchant_ref": "M1",
    "channel": "ecommerce",
    "entry_mode": "manual",
}

for label, value in [("NaN", float("nan")),
                     ("inf", float("inf")),
                     ("-inf", float("-inf")),
                     ("1e-300", 1e-300),
                     ("normal 100.0", 100.0)]:
    try:
        ScoreRequest(**{**BASE, "amount": value})
        print(f"  {label:<14} ACCEPTED")
    except Exception as e:
        first = str(e).splitlines()
        msg = next((l.strip() for l in first if "finite" in l or "Value error" in l),
                   first[0] if first else "")
        print(f"  {label:<14} REJECTED  {msg[:70]}")