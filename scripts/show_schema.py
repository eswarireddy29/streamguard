"""Print the columns of the decision and case tables."""

import pandas as pd
from sqlalchemy import text

from streamguard.db.session import get_session

TABLES = ["decisions", "cases", "case_events", "transactions"]

with get_session() as s:
    for t in TABLES:
        q = text("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = :t
            ORDER BY ordinal_position
        """)
        df = pd.read_sql(q, s.connection(), params={"t": t})
        print("=" * 72)
        print(f"{t}  ({len(df)} columns)")
        print("=" * 72)
        if len(df):
            print(df.to_string(index=False))
        else:
            print("  TABLE NOT FOUND")
        print()

    counts = text("""
        SELECT 'transactions' AS t, COUNT(*) AS n FROM transactions
        UNION ALL SELECT 'decisions', COUNT(*) FROM decisions
        UNION ALL SELECT 'cases', COUNT(*) FROM cases
        UNION ALL SELECT 'case_events', COUNT(*) FROM case_events
    """)
    print("=" * 72)
    print("ROW COUNTS")
    print("=" * 72)
    print(pd.read_sql(counts, s.connection()).to_string(index=False))