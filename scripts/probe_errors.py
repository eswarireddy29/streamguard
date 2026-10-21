"""
scripts/probe_errors.py

Task 29 - what breaks when the input is hostile or malformed?

Task 28 tested the contract working correctly. This probes the edges:
oversized payloads, wrong types, injection attempts, unicode, absent
resources, concurrent writes. Each case states what SHOULD happen.

Nothing here is a fix. It is a survey, so the hardening that follows
addresses confirmed problems rather than imagined ones.

Runs in-process via TestClient - no server needed.

    python scripts/probe_errors.py
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import typer
from fastapi.testclient import TestClient

from streamguard.api.auth import Role, UserStore, create_token
from streamguard.utils.logging_config import setup_logging

app = typer.Typer(add_completion=False)
LINE = "=" * 72

VALID = {
    "transaction_ref": "PROBE001",
    "occurred_at": "2026-03-20T14:30:00+05:30",
    "card_ref": "CARD0000001",
    "customer_ref": "CUST0000001",
    "merchant_ref": "MERCH000001",
    "amount": 100.0,
    "channel": "ecommerce",
    "entry_mode": "manual",
}


def setup():
    import streamguard.api.main as m
    m._users = UserStore()
    m._users.add("alice", "analyst-password", Role.ANALYST)
    m._users.add("bob", "manager-password", Role.RISK_MANAGER)
    m._users.add("switch", "service-password", Role.SERVICE)
    client = TestClient(m.app, raise_server_exceptions=False)
    tokens = {
        u: create_token(m._users.users[u])["access_token"]
        for u in ("alice", "bob", "switch")
    }
    return m, client, tokens


class Probe:
    def __init__(self):
        self.results = []

    def check(self, name: str, expected, got, note: str = ""):
        # A list of ACCEPTABLE status codes means membership; a list
        # passed as the VALUE (the leak checks) means equality.
        if isinstance(expected, (list, tuple, set)) and \
                not isinstance(got, (list, tuple, set)):
            ok = got in expected
        else:
            ok = got == expected
        self.results.append((name, expected, got, ok, note))
        exp = "/".join(str(e) for e in expected) \
            if isinstance(expected, (list, tuple, set)) else str(expected)
        mark = "" if ok else "   <-- UNEXPECTED"
        print(f"  {name:<44}{exp:>10}{str(got):>7}{mark}")
        if note and not ok:
            print(f"      {note}")

    def report(self):
        bad = [r for r in self.results if not r[3]]
        print()
        print(LINE)
        print(f"  {len(self.results)} probes, {len(bad)} unexpected")
        print(LINE)
        if bad:
            print()
            print("  NEEDS ATTENTION:")
            for name, exp, got, _, note in bad:
                print(f"    {name}: expected {exp}, got {got}")
                if note:
                    print(f"      {note}")
        return len(bad)


@app.command()
def main() -> None:
    setup_logging()
    m, client, tokens = setup()
    p = Probe()

    def hdr(user="switch"):
        return {"Authorization": f"Bearer {tokens[user]}"}

    print(LINE)
    print("TASK 29 - ERROR HANDLING PROBE")
    print(LINE)
    print()
    print(f"  {'probe':<44}{'expect':>10}{'got':>7}")
    print("  " + "-" * 61)

    # ---- malformed input ---------------------------------------------
    print()
    print("  MALFORMED INPUT")
    r = client.post("/score", content=b"{not json",
                    headers={**hdr(), "Content-Type": "application/json"})
    p.check("broken JSON", 422, r.status_code)

    r = client.post("/score", json=[], headers=hdr())
    p.check("array instead of object", 422, r.status_code)

    r = client.post("/score", json={}, headers=hdr())
    p.check("empty object", 422, r.status_code)

    r = client.post("/score", json={**VALID, "amount": "lots"},
                    headers=hdr())
    p.check("amount as a string", 422, r.status_code)

    r = client.post("/score", json={**VALID, "amount": None},
                    headers=hdr())
    p.check("amount null", 422, r.status_code)

    r = client.post("/score", json={**VALID, "occurred_at": "not-a-date"},
                    headers=hdr())
    p.check("unparseable date", 422, r.status_code)

    # ---- numeric edges -------------------------------------------------
    print()
    print("  NUMERIC EDGES")
    for label, value in [("amount zero", 0.0),
                         ("amount negative", -100.0),
                         ("amount enormous", 1e300),
                         ("amount tiny", 1e-300)]:
        r = client.post("/score", json={**VALID, "amount": value},
                        headers=hdr())
        p.check(label, (200, 422), r.status_code)

    r = client.post("/score",
                    content=json.dumps({**VALID, "amount": float("nan")}
                                       ).replace("NaN", "NaN").encode(),
                    headers={**hdr(), "Content-Type": "application/json"})
    p.check("amount NaN", (400, 422), r.status_code,
            "NaN must not reach the model")

    r = client.post("/score", json={**VALID, "lat": 999.0}, headers=hdr())
    p.check("latitude out of range", 422, r.status_code)

    # ---- oversized ------------------------------------------------------
    print()
    print("  OVERSIZED INPUT")
    r = client.post("/score", json={**VALID, "transaction_ref": "X" * 10_000},
                    headers=hdr())
    p.check("10KB transaction_ref", 422, r.status_code)

    r = client.post("/score", json={**VALID, "city": "X" * 100_000},
                    headers=hdr())
    p.check("100KB city", (200, 422), r.status_code,
            "an unbounded string field is a memory risk")

    r = client.post("/auth/token",
                    json={"username": "a" * 100_000, "password": "x"})
    p.check("100KB username", 422, r.status_code)

    # ---- injection attempts ---------------------------------------------
    print()
    print("  INJECTION ATTEMPTS")
    r = client.get("/cases/'; DROP TABLE cases; --",
                   headers=hdr("alice"))
    p.check("SQL in a path parameter", (404, 422), r.status_code,
            "parameterised queries should make this harmless")

    r = client.post("/score",
                    json={**VALID, "card_ref": "'; DROP TABLE cards; --"},
                    headers=hdr())
    p.check("SQL in a field", (200, 422, 500), r.status_code)

    r = client.get("/cases?limit=-1", headers=hdr("alice"))
    p.check("negative limit", (200, 422), r.status_code,
            "a negative LIMIT is a database error")

    r = client.get("/cases?limit=99999999", headers=hdr("alice"))
    p.check("enormous limit", (200, 422), r.status_code,
            "an unbounded limit lets one request read the whole table")

    r = client.get("/cases?status=../../etc/passwd", headers=hdr("alice"))
    p.check("path traversal in status", (200, 422), r.status_code)

    # ---- unicode ---------------------------------------------------------
    print()
    print("  UNICODE AND ENCODING")
    r = client.post("/score", json={**VALID, "city": "\u0645\u0646\u0628\u0626"},
                    headers=hdr())
    p.check("arabic city name", (200, 422), r.status_code)

    r = client.post("/score", json={**VALID, "city": "\x00null byte"},
                    headers=hdr())
    p.check("null byte in a string", (200, 422, 500), r.status_code,
            "PostgreSQL rejects \\x00 in text columns")

    r = client.post("/score", json={**VALID, "city": "caf\u00e9 \U0001F600"},
                    headers=hdr())
    p.check("emoji", (200, 422), r.status_code)

    # ---- missing resources ------------------------------------------------
    print()
    print("  MISSING RESOURCES")
    r = client.get("/cases/DOES_NOT_EXIST", headers=hdr("alice"))
    p.check("unknown case", 404, r.status_code)

    r = client.post("/cases/DOES_NOT_EXIST/assign", json={},
                    headers=hdr("alice"))
    p.check("assign unknown case", 400, r.status_code)

    r = client.post("/cases/DOES_NOT_EXIST/verdict",
                    json={"verdict": "confirmed_fraud"},
                    headers=hdr("alice"))
    p.check("verdict on unknown case", 400, r.status_code)

    r = client.get("/no-such-endpoint", headers=hdr("alice"))
    p.check("unknown endpoint", 404, r.status_code)

    # ---- auth edges --------------------------------------------------------
    print()
    print("  AUTH EDGES")
    r = client.get("/cases", headers={"Authorization": "Bearer "})
    p.check("empty bearer", 401, r.status_code)

    r = client.get("/cases", headers={"Authorization": tokens["alice"]})
    p.check("token without 'Bearer'", 401, r.status_code)

    r = client.get("/cases", headers={"Authorization": "Basic abc123"})
    p.check("wrong auth scheme", 401, r.status_code)

    r = client.get("/cases",
                   headers={"Authorization": f"Bearer {tokens['alice']}x"})
    p.check("token with a trailing char", 401, r.status_code)

    # ---- error body shape ---------------------------------------------------
    print()
    print("  ERROR BODY SHAPE")
    r = client.get("/cases/DOES_NOT_EXIST", headers=hdr("alice"))
    body = r.text
    leaks = [w for w in ("Traceback", "sqlalchemy", "psycopg",
                         "File \"", "streamguard/", "StreamGuard2026")
             if w in body]
    p.check("404 body leaks internals", [], leaks,
            f"leaked: {leaks}" if leaks else "")

    r = client.get("/cases?limit=-1", headers=hdr("alice"))
    leaks = [w for w in ("Traceback", "sqlalchemy", "psycopg",
                         "StreamGuard2026") if w in r.text]
    p.check("bad-limit body leaks internals", [], leaks,
            f"leaked: {leaks}" if leaks else "")

    bad = p.report()
    print()
    print("  Each UNEXPECTED is a candidate for hardening in 29.2.")
    print("  Some may be acceptable once understood - a 200 on an odd")
    print("  input is fine if the value is handled safely.")
    print(LINE)
    raise typer.Exit(0)


if __name__ == "__main__":
    app()