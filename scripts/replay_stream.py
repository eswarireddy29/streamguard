"""
scripts/replay_stream.py

Task 25 - feed the scoring API from the event log, at a chosen rate.

WHY THIS EXISTS. The event log holds 791,109 transactions but nothing
replays them into the API. A "live stream" page with no stream behind
it would be a mock, and the project record forbids replacing a hard
feature with a placeholder.

This is also what makes the Phase F demo honest: the dashboard shows
real decisions on real transactions, produced by the same code path a
payment switch would use.

    uvicorn streamguard.api.main:app --port 8000     (terminal 1)
    python scripts/replay_stream.py                   (terminal 2)
    python scripts/replay_stream.py --rate 20 --skip 200000
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

import typer

from streamguard.eventlog.consumer import FileEventConsumer
from streamguard.ml.splitter import PROJECT_ROOT
from streamguard.utils.logging_config import get_logger, setup_logging

app = typer.Typer(add_completion=False)
log = get_logger(__name__)
LINE = "=" * 72

_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
urllib.request.install_opener(_opener)

# Fields the API schema accepts. is_fraud and fraud_type are stripped:
# the schema rejects them (Task 23 security rule) and a payment switch
# would not have them anyway.
ALLOWED = {
    "transaction_ref", "occurred_at", "card_ref", "customer_ref",
    "merchant_ref", "amount", "currency", "channel", "entry_mode",
    "device_ref", "device_type", "card_type", "city", "country",
    "lat", "lon", "home_city", "home_country", "home_lat", "home_lon",
    "mcc", "merchant_category", "merchant_is_online", "merchant_city",
    "merchant_country",
}


def post(url: str, body: dict, token: str):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}
    except Exception as exc:
        return 0, {"detail": str(exc)}


@app.command()
def main(
    host: str = typer.Option("http://127.0.0.1:8000"),
    rate: float = typer.Option(5.0, help="Transactions per second"),
    limit: int = typer.Option(0, help="Stop after N (0 = run forever)"),
    skip: int = typer.Option(200_000,
                             help="Start here; match the server's warm point"),
    username: str = typer.Option("payment-switch"),
    password: str = typer.Option("switch-dev-password"),
) -> None:
    setup_logging()
    print(LINE)
    print("TASK 25 - REPLAY FEEDER")
    print(LINE)

    # The SERVICE role, because that is what a payment switch is.
    # It can score and nothing else - verified at Task 23.
    code, auth = post(f"{host}/auth/token",
                      {"username": username, "password": password}, "")
    if code != 200:
        print(f"\n  ERROR: login failed ({code}) {auth}")
        print("  Is the API running?")
        raise typer.Exit(1)
    token = auth["access_token"]

    print()
    print(f"  host      {host}")
    print(f"  as        {username} (role: {auth['role']})")
    print(f"  rate      {rate}/sec")
    print(f"  skip      {skip:,} events")
    print()
    print("  The server must be warmed to the SAME offset, or every")
    print("  card arrives with a stale last-seen time and the decision")
    print("  mix is nonsense (Task 20 learned this the hard way).")
    print()
    print("  Ctrl+C to stop.")
    print()

    consumer = FileEventConsumer(
        PROJECT_ROOT / "data" / "events", topic="transactions",
        group=f"replay_{int(time.time())}", from_beginning=True)

    interval = 1.0 / rate if rate > 0 else 0.0
    seen = sent = 0
    counts = {"approve": 0, "review": 0, "block": 0}
    errors = 0
    started = time.time()

    try:
        for ev in consumer.stream():
            seen += 1
            if seen <= skip:
                continue

            body = {k: v for k, v in ev.payload.items() if k in ALLOWED}
            t0 = time.perf_counter()
            code, resp = post(f"{host}/score", body, token)

            if code == 200:
                sent += 1
                counts[resp.get("decision", "approve")] = counts.get(
                    resp.get("decision", "approve"), 0) + 1
                if resp.get("decision") != "approve":
                    print(f"  {datetime.now(timezone.utc).strftime('%H:%M:%S')}  "
                          f"{resp['decision'].upper():<8} "
                          f"p={resp['probability']:.4f}  "
                          f"{body['transaction_ref']}  "
                          f"{body.get('city', '?')}  "
                          f"Rs {body['amount']:,.0f}")
            else:
                errors += 1
                if errors <= 3:
                    print(f"  {code}: {resp}")

            if sent and sent % 100 == 0:
                elapsed = time.time() - started
                print(f"  --- {sent:,} sent, {elapsed:.0f}s, "
                      f"{sent / elapsed:.1f}/s, {counts}")

            if limit and sent >= limit:
                break

            spent = time.perf_counter() - t0
            if interval > spent:
                time.sleep(interval - spent)

    except KeyboardInterrupt:
        print("\n  stopped")

    elapsed = time.time() - started
    print()
    print(LINE)
    print(f"  sent        {sent:,} in {elapsed:.0f}s "
          f"({sent / elapsed if elapsed else 0:.1f}/s)")
    print(f"  decisions   {counts}")
    print(f"  errors      {errors}")
    print(LINE)


if __name__ == "__main__":
    app()