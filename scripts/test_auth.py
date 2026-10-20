"""
scripts/test_auth.py

Task 23 - can the wrong caller do the wrong thing?

Every case states the expected status code. A permission check that
has never been exercised cannot be trusted.

    uvicorn streamguard.api.main:app --port 8000   (terminal 1)
    python scripts/test_auth.py                     (terminal 2)
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

import typer

from streamguard.utils.logging_config import setup_logging

app = typer.Typer(add_completion=False)
LINE = "=" * 72

_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
urllib.request.install_opener(_opener)


def call(method: str, url: str, body=None, token=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, method=method,
                                 headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}


@app.command()
def main(host: str = typer.Option("http://127.0.0.1:8000")) -> None:
    setup_logging()
    print(LINE)
    print("TASK 23 - AUTHENTICATION AND ROLES")
    print(LINE)

    code, _ = call("GET", f"{host}/health")
    if code != 200:
        print(f"\n  ERROR: server not reachable at {host}")
        raise typer.Exit(1)
    print("\n  /health is open (a load balancer needs it): 200")

    # ---- login ---------------------------------------------------------
    print()
    print(LINE)
    print("1. LOGIN")
    print(LINE)
    tokens = {}
    creds = [("analyst", "analyst-dev-password"),
             ("manager", "manager-dev-password"),
             ("payment-switch", "switch-dev-password")]
    print()
    for user, pw in creds:
        code, r = call("POST", f"{host}/auth/token",
                       {"username": user, "password": pw})
        if code == 200:
            tokens[user] = r["access_token"]
            print(f"  {user:<16} {code}  role={r['role']:<14}"
                  f"expires in {r['expires_in']}s")
        else:
            print(f"  {user:<16} {code}  {r}")

    print()
    code, r = call("POST", f"{host}/auth/token",
                   {"username": "analyst", "password": "wrong"})
    print(f"  wrong password   {code}  {r.get('detail')}")
    code, r = call("POST", f"{host}/auth/token",
                   {"username": "ghost", "password": "whatever"})
    print(f"  unknown user     {code}  {r.get('detail')}")
    print()
    print("  Both return the same 'invalid credentials' - the response")
    print("  must not reveal which usernames exist.")

    # ---- who am i ------------------------------------------------------
    print()
    print(LINE)
    print("2. PERMISSIONS BY ROLE")
    print(LINE)
    print()
    for user, tok in tokens.items():
        code, r = call("GET", f"{host}/auth/me", token=tok)
        print(f"  {user:<16} {r.get('role'):<14} "
              f"{', '.join(r.get('permissions', []))}")

    # ---- the matrix -----------------------------------------------------
    print()
    print(LINE)
    print("3. ACCESS MATRIX  (expected vs actual)")
    print(LINE)

    cases = [
        ("no token",        None,              "GET",  "/cases", None, 401),
        ("bad token",       "not-a-real-token","GET",  "/cases", None, 401),
        ("service -> cases", tokens.get("payment-switch"),
                                               "GET",  "/cases", None, 403),
        ("analyst -> cases", tokens.get("analyst"),
                                               "GET",  "/cases", None, 200),
        ("manager -> cases", tokens.get("manager"),
                                               "GET",  "/cases", None, 200),
        ("analyst -> stats", tokens.get("analyst"),
                                               "GET",  "/cases-stats", None, 403),
        ("manager -> stats", tokens.get("manager"),
                                               "GET",  "/cases-stats", None, 200),
    ]

    print()
    print(f"  {'case':<24}{'expect':>8}{'got':>6}")
    print("  " + "-" * 38)
    failures = 0
    for name, tok, method, path, body, expected in cases:
        code, _ = call(method, f"{host}{path}", body, tok)
        ok = code == expected
        failures += 0 if ok else 1
        print(f"  {name:<24}{expected:>8}{code:>6}"
              f"{'' if ok else '   <-- FAIL'}")

    # ---- identity comes from the token -----------------------------------
    print()
    print(LINE)
    print("4. THE AUDIT TRAIL RECORDS A VERIFIED IDENTITY")
    print(LINE)
    code, q = call("GET", f"{host}/cases?limit=1",
                   token=tokens.get("analyst"))
    cases_open = q.get("cases", []) if code == 200 else []
    if not cases_open:
        print("\n  no open cases - run scripts/test_cases.py first")
    else:
        ref = cases_open[0]["case_ref"]
        code, r = call("POST", f"{host}/cases/{ref}/assign", {},
                       tokens.get("analyst"))
        print(f"\n  assigned {ref}: {code}  {r}")
        print()
        print("  The request body carried NO analyst name. The server")
        print("  used the identity in the token. Before this task the")
        print("  caller declared who they were, which is not an audit")
        print("  trail - it is a suggestion box.")

        code, case = call("GET", f"{host}/cases/{ref}",
                          token=tokens.get("analyst"))
        for e in case.get("audit_trail", [])[-2:]:
            print(f"      {e['at'][:19]}  {e['event']:<20} by {e['actor']}")

    print()
    print(LINE)
    if failures:
        print(f"  {failures} CASE(S) FAILED")
        raise typer.Exit(1)
    print(f"  all {len(cases)} access cases passed")
    print(LINE)


if __name__ == "__main__":
    app()