"""Show the 8 fraud rows that share a card and timestamp."""

import pandas as pd
from streamguard.ml.splitter import split
from streamguard.utils.logging_config import setup_logging

setup_logging()
blocks = split(save_manifest=False)
meta = blocks["train"].meta.reset_index(drop=True)

card_col = next(c for c in ("card_ref", "card_id") if c in meta.columns)
fraud = meta[meta["fraud_type"].notna()]

dupe_keys = fraud[fraud.duplicated(subset=[card_col, "_local_time"], keep=False)]

cols = [c for c in (card_col, "_local_time", "transaction_ref",
                    "fraud_type", "is_fraud", "offset") if c in meta.columns]

print(f"\n{len(dupe_keys)} fraud rows in duplicate groups:\n")
print(dupe_keys[cols].sort_values([card_col, "_local_time"]).to_string(index=False))

print("\n\nALL rows (fraud and normal) on those cards at those times:\n")
for _, r in dupe_keys.drop_duplicates(subset=[card_col, "_local_time"]).iterrows():
    m = (meta[card_col] == r[card_col]) & (meta["_local_time"] == r["_local_time"])
    print(meta.loc[m, cols].to_string(index=False))
    print()