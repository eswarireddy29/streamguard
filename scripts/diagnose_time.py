"""
scripts/diagnose_time.py

Task 13.7C - why do 62.6% of CNP rows have seconds_since_prev = 0?

A zero time gap divides into the 99,999 speed sentinel. Either two
transactions on the same card share a timestamp, or the previous-
transaction state is not being set. This looks at the raw rows.

Read-only. Queries the database directly.

    python scripts/diagnose_time.py
"""

from __future__ import annotations

import pandas as pd
import typer
from sqlalchemy import text

from streamguard.db.session import get_session
from streamguard.utils.logging_config import setup_logging

app = typer.Typer(add_completion=False)
LINE = "=" * 72


@app.command()
def main(limit: int = typer.Option(25)) -> None:
    setup_logging()
    print(LINE)
    print("TASK 13.7C - DUPLICATE TIMESTAMP DIAGNOSTIC")
    print(LINE)

    with get_session() as s:
        # 1. How many cards have two transactions at the same instant?
        q1 = text("""
            SELECT fraud_type, COUNT(*) AS n_dupe_pairs
            FROM (
                SELECT card_id, occurred_at, fraud_type, COUNT(*) AS c
                FROM transactions
                GROUP BY card_id, occurred_at, fraud_type
                HAVING COUNT(*) > 1
            ) d
            GROUP BY fraud_type
            ORDER BY n_dupe_pairs DESC
        """)
        print()
        print("1. SAME card_id + SAME occurred_at, by fraud_type:")
        print()
        df1 = pd.read_sql(q1, s.connection())
        print(df1.to_string(index=False) if len(df1) else "  none")

        # 2. Sample CNP episodes with their timestamps
        q2 = text("""
            SELECT card_id, transaction_ref, occurred_at, amount, merchant_id
            FROM transactions
            WHERE fraud_type = 'card_not_present'
              AND card_id IN (
                SELECT card_id FROM transactions
                WHERE fraud_type = 'card_not_present'
                GROUP BY card_id HAVING COUNT(*) > 1
                LIMIT 4
              )
            ORDER BY card_id, occurred_at
            LIMIT :lim
        """)
        print()
        print("2. SAMPLE CNP EPISODES (look at the occurred_at gaps):")
        print()
        df2 = pd.read_sql(q2, s.connection(), params={"lim": limit})
        print(df2.to_string(index=False) if len(df2) else "  none")

        # 3. Does the whole table have duplicate (card, time) pairs?
        q3 = text("""
            SELECT
                COUNT(*) FILTER (WHERE c > 1) AS dupe_groups,
                COUNT(*) AS total_groups
            FROM (
                SELECT card_id, occurred_at, COUNT(*) AS c
                FROM transactions GROUP BY card_id, occurred_at
            ) g
        """)
        print()
        print("3. WHOLE TABLE:")
        print()
        print(pd.read_sql(q3, s.connection()).to_string(index=False))

        # 4. Gap distribution for CNP, straight from the database
        q4 = text("""
            SELECT
                EXTRACT(EPOCH FROM (occurred_at - prev)) AS gap_seconds
            FROM (
                SELECT occurred_at,
                       LAG(occurred_at) OVER (
                           PARTITION BY card_id ORDER BY occurred_at
                       ) AS prev,
                       fraud_type
                FROM transactions
            ) t
            WHERE fraud_type = 'card_not_present' AND prev IS NOT NULL
        """)
        print()
        print("4. CNP GAP SECONDS (from the database, not the features):")
        print()
        df4 = pd.read_sql(q4, s.connection())
        if len(df4):
            print(df4["gap_seconds"].describe(
                percentiles=[0.1, 0.25, 0.5, 0.75]
            ).to_string())
            print()
            print(f"  gaps of exactly 0: {(df4['gap_seconds'] == 0).sum():,}"
                  f" of {len(df4):,}")
        else:
            print("  none")

    print()
    print(LINE)


if __name__ == "__main__":
    app()