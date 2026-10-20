"""Did any verdict reach the database?"""

import pandas as pd
from sqlalchemy import text

from streamguard.db.session import get_session

with get_session() as s:
    df = pd.read_sql(
        text("""
            SELECT case_ref, status, verdict, assigned_to, verdict_at, notes
            FROM cases
            WHERE verdict != 'pending'
            ORDER BY id DESC
            LIMIT 10
        """),
        s.connection(),
    )
    total = s.execute(text("SELECT COUNT(*) FROM cases")).scalar()
    events = s.execute(
        text("SELECT COUNT(*) FROM case_events "
             "WHERE event_type = 'verdict_submitted'")).scalar()

print(f"cases total            : {total}")
print(f"verdict_submitted logs : {events}")
print()
if len(df):
    print(df.to_string(index=False))
else:
    print("NO VERDICTS IN THE DATABASE")