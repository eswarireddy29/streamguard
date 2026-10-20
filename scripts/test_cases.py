"""
scripts/test_cases.py

Task 22 - end-to-end case lifecycle against a running server.

    uvicorn streamguard.api.main:app --port 8000     (terminal 1)
    python scripts/test_cases.py                      (terminal 2)
"""

from __future__ import annotations

import json
import urllib.request
import urllib.error

import pandas as pd
import typer
from sqlalchemy import text

from streamguard.db.session import get_session
from streamguard.utils.logging_config import setup_logging

app = typer.Typer(add_completion=False)
LINE = "=" * 72

_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
urllib.request.install_opener(_opener)


def call(method: str, url: str, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


@app.command()
def main(host: str = typer.Option("http://127.0.0.1:8000"),
         analyst: str = typer.Option("analyst_lasya")) -> None:
    setup_logging()
    print(LINE)
    print("TASK 22 - CASE LIFECYCLE")
    print(LINE)

    code, _ = call("GET", f"{host}/health")
    if code != 200:
        print(f"\n  ERROR: server not reachable at {host}")
        raise typer.Exit(1)

    # ---- 1. score real transactions so a case can be opened ----------
    with get_session() as s:
        refs = [r[0] for r in s.execute(text("""
            SELECT t.transaction_ref FROM transactions t
            WHERE t.is_fraud = true
            ORDER BY t.occurred_at DESC LIMIT 12
        """)).fetchall()]
        rows = pd.read_sql(text("""
            SELECT t.transaction_ref, t.occurred_at, c.card_ref,
                   cu.customer_ref, m.merchant_ref, d.device_ref,
                   t.amount, t.currency, t.channel, t.entry_mode,
                   t.city, t.country, t.lat, t.lon,
                   cu.home_city, cu.home_country, cu.home_lat, cu.home_lon,
                   m.mcc, m.category AS merchant_category,
                   m.is_online AS merchant_is_online,
                   m.city AS merchant_city, m.country AS merchant_country
            FROM transactions t
            JOIN cards c ON c.id = t.card_id
            JOIN customers cu ON cu.id = t.customer_id
            JOIN merchants m ON m.id = t.merchant_id
            LEFT JOIN devices d ON d.id = t.device_id
            WHERE t.transaction_ref = ANY(:refs)
        """), s.connection(), params={"refs": refs})

    print()
    print(f"  scoring {len(rows)} known-fraud transactions")

    opened = 0
    for _, r in rows.iterrows():
        body = {k: (None if pd.isna(v) else v) for k, v in r.items()}
        body["occurred_at"] = pd.Timestamp(r["occurred_at"]).isoformat()
        body["amount"] = float(r["amount"])
        body["merchant_is_online"] = bool(r["merchant_is_online"])
        code, resp = call("POST", f"{host}/score", body)
        if code == 200 and resp.get("decision") != "approve":
            opened += 1
        elif code != 200:
            print(f"  {code}: {resp}")

    print(f"  flagged (case opened): {opened}")

    # ---- 2. the queue -------------------------------------------------
    print()
    print(LINE)
    print("1. ANALYST QUEUE  (priority = score x amount)")
    print(LINE)
    code, q = call("GET", f"{host}/cases?limit=10")
    print()
    print(f"  {'case_ref':<16}{'pri':>5}{'score':>9}{'amount':>12}"
          f"{'action':>9}")
    print("  " + "-" * 51)
    for c in q.get("cases", []):
        print(f"  {c['case_ref']:<16}{c['priority']:>5}{c['score']:>9.4f}"
              f"{c['amount']:>12,.0f}{c['action']:>9}")

    if not q.get("cases"):
        print("  no open cases - nothing was flagged")
        raise typer.Exit(0)

    ref = q["cases"][0]["case_ref"]

    # ---- 3. assign ------------------------------------------------------
    print()
    print(LINE)
    print(f"2. ASSIGN {ref} TO {analyst}")
    print(LINE)
    code, a = call("POST", f"{host}/cases/{ref}/assign",
                   {"analyst": analyst})
    print(f"\n  {code}  {a}")

    # ---- 4. the investigation view -------------------------------------
    print()
    print(LINE)
    print(f"3. CASE DETAIL  {ref}")
    print(LINE)
    code, case = call("GET", f"{host}/cases/{ref}")
    print()
    print(f"  transaction   {case['transaction_ref']}")
    print(f"  score         {case['score']:.4f}")
    print(f"  amount        {case['amount']:,.2f}")
    print(f"  status        {case['status']}")
    print(f"  assigned      {case['assigned_to']}")
    print(f"  model         {case['model_version']}  "
          f"({case['n_features']} features stored)")
    expl = case.get("explanation") or {}
    print()
    print("  why it was flagged:")
    for t in (expl.get("top_reasons") or [])[:5]:
        print(f"      {t['feature']:<28} = {t['value']:>12,.2f}   "
              f"SHAP {t['shap']:+.4f}")
    if expl.get("rules_fired"):
        print()
        print("  rules fired:")
        for r in expl["rules_fired"]:
            print(f"      {r['rule']} -> {r['decision']}: {r['reason']}")

    # ---- 5. verdict ------------------------------------------------------
    print()
    print(LINE)
    print("4. SUBMIT VERDICT")
    print(LINE)
    code, v = call("POST", f"{host}/cases/{ref}/verdict", {
        "analyst": analyst, "verdict": "confirmed_fraud",
        "notes": "Manual entry, far from home, 3am. Confirmed with customer.",
    })
    print(f"\n  {code}  {v}")

    print()
    print("  submitting again (should be refused - already closed):")
    code, v2 = call("POST", f"{host}/cases/{ref}/verdict", {
        "analyst": analyst, "verdict": "legitimate"})
    print(f"  {code}  {v2}")

    print()
    print("  invalid verdict (should be refused):")
    code, v3 = call("POST", f"{host}/cases/{ref}/verdict", {
        "analyst": analyst, "verdict": "probably_fine"})
    print(f"  {code}  {v3}")

    # ---- 6. audit trail --------------------------------------------------
    print()
    print(LINE)
    print("5. AUDIT TRAIL")
    print(LINE)
    code, case = call("GET", f"{host}/cases/{ref}")
    print()
    for e in case.get("audit_trail", []):
        print(f"  {e['at'][:19]}  {e['event']:<20} by {e['actor']}")
        print(f"      {e['payload']}")

    # ---- 7. stats --------------------------------------------------------
    print()
    print(LINE)
    print("6. STATS")
    print(LINE)
    code, st = call("GET", f"{host}/cases-stats")
    print()
    print(f"  decisions        {st['decisions']}")
    print(f"  cases            {st['cases']}")
    print(f"  labels available {st['labels_available']}")
    print(f"  audit events     {st['audit_events']}")
    print()
    print("  'labels available' is what Task 30 retrains on.")
    print(LINE)


if __name__ == "__main__":
    app()