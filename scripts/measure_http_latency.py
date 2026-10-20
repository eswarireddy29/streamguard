"""
scripts/measure_http_latency.py

Task 20.4 - what does HTTP add on top of in-process scoring?

20.3 measured the scorer directly: p50 0.69 ms. The Task 19 manual
test over HTTP showed 46.7 ms. The difference is FastAPI, Pydantic
validation, JSON serialisation and loopback networking. This measures
that gap instead of assuming it.

REQUIRES THE SERVER TO BE RUNNING in another terminal:
    uvicorn streamguard.api.main:app --port 8000

    python scripts/measure_http_latency.py
    python scripts/measure_http_latency.py --n 500 --concurrency 4
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import typer
import urllib.error
import urllib.request

from streamguard.api.bench import summarize, HEADER, RULE
from streamguard.eventlog.consumer import FileEventConsumer
from streamguard.ml.splitter import PROJECT_ROOT
from streamguard.utils.logging_config import get_logger, setup_logging

app = typer.Typer(add_completion=False)
log = get_logger(__name__)

REPORTS_DIR = PROJECT_ROOT / "reports"
LINE = "=" * 72
BUDGET_MS = 100.0

# Fields the API schema accepts. Anything else is rejected by
# extra="forbid", which is the Task 19 security rule working.
ALLOWED = {
    "transaction_ref", "occurred_at", "card_ref", "customer_ref",
    "merchant_ref", "amount", "currency", "channel", "entry_mode",
    "device_ref", "device_type", "card_type", "city", "country",
    "lat", "lon", "home_city", "home_country", "home_lat", "home_lon",
    "mcc", "merchant_category", "merchant_is_online", "merchant_city",
    "merchant_country",
}

# Windows urllib reads system proxy settings and will try to route
# even 127.0.0.1 through a configured proxy, which refuses the
# connection. curl.exe bypasses proxies for loopback; urllib does not.
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
urllib.request.install_opener(_opener)
def post(url: str, body: dict, timeout: float = 30.0) -> tuple:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"}, method="POST")
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        ms = (time.perf_counter() - t0) * 1000
        return ms, payload, None
    except urllib.error.HTTPError as exc:
        ms = (time.perf_counter() - t0) * 1000
        return ms, None, f"HTTP {exc.code}"
    except Exception as exc:
        ms = (time.perf_counter() - t0) * 1000
        return ms, None, str(exc)


@app.command()
def main(
    host: str = typer.Option("http://127.0.0.1:8000"),
    n: int = typer.Option(500, help="Requests to send"),
    concurrency: int = typer.Option(1, help="Parallel clients"),
    skip: int = typer.Option(200_000, help="Skip this many events"),
) -> None:
    setup_logging()
    print(LINE)
    print("TASK 20.4 - HTTP LATENCY")
    print(LINE)

    # ---- is the server up? ------------------------------------------------
    try:
        with urllib.request.urlopen(f"{host}/health", timeout=10) as r:
            health = json.loads(r.read().decode("utf-8"))
    except Exception as exc:
        print()
        print(f"  ERROR: cannot reach {host} - {exc}")
        print()
        print("  Start the server in ANOTHER terminal first:")
        print("      uvicorn streamguard.api.main:app --port 8000")
        raise typer.Exit(1)

    print()
    print(f"  host          {host}")
    print(f"  model         {health.get('model_version')}")
    print(f"  state         {health.get('cards_in_state'):,} cards")
    print(f"  requests      {n:,}")
    print(f"  concurrency   {concurrency}")

    # ---- build request bodies ---------------------------------------------
    root = PROJECT_ROOT / "data" / "events"
    consumer = FileEventConsumer(root, topic="transactions",
                                 group=f"http_bench_{int(time.time())}",
                                 from_beginning=True)
    run_id = int(time.time()) % 1_000_000
    bodies = []
    seen = 0
    for ev in consumer.stream():
        seen += 1
        if seen <= skip:
            continue
        p = {k: v for k, v in ev.payload.items() if k in ALLOWED}
        # Unique per RUN, not just per request - a second run with the
        # same refs hits the Task 19 idempotency cache and measures a
        # dict lookup instead of the scoring path.
        p["transaction_ref"] = f"BENCH{run_id}{seen:09d}"
        bodies.append(p)
        if len(bodies) >= n:
            break
        
    url = f"{host}/score"

    # ---- warm the connection ----------------------------------------------
    for b in bodies[:5]:
        post(url, b)

    # ---- measure -----------------------------------------------------------
    print()
    print("  sending...")
    samples, errors, decisions = [], {}, {}
    server_ms = []

    t_start = time.perf_counter()
    if concurrency <= 1:
        for b in bodies:
            ms, payload, err = post(url, b)
            samples.append(ms)
            if err:
                errors[err] = errors.get(err, 0) + 1
            elif payload:
                d = payload.get("decision", "?")
                decisions[d] = decisions.get(d, 0) + 1
                server_ms.append(float(payload.get("latency_ms", 0.0)))
    else:
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            for ms, payload, err in pool.map(lambda b: post(url, b), bodies):
                samples.append(ms)
                if err:
                    errors[err] = errors.get(err, 0) + 1
                elif payload:
                    d = payload.get("decision", "?")
                    decisions[d] = decisions.get(d, 0) + 1
                    server_ms.append(float(payload.get("latency_ms", 0.0)))
    wall = time.perf_counter() - t_start

    # ---- report -------------------------------------------------------------
    client = summarize("client (round trip)", samples)
    server = summarize("server (scoring only)", server_ms)

    print()
    print(LINE)
    print("1. CLIENT vs SERVER")
    print(LINE)
    print()
    print(HEADER)
    print(RULE)
    print(client.line())
    if server.n:
        print(server.line())
    print()
    if server.n:
        overhead = client.p50_ms - server.p50_ms
        print(f"  HTTP overhead at p50: {overhead:.2f} ms "
              f"({100 * overhead / client.p50_ms:.0f}% of the round trip)")
        print()
        print("  That is FastAPI routing, Pydantic validation, JSON")
        print("  serialisation and loopback networking - not the model.")

    print()
    print(LINE)
    print("2. THROUGHPUT")
    print(LINE)
    print()
    print(f"  requests      {len(samples):,}")
    print(f"  wall clock    {wall:.2f}s")
    print(f"  throughput    {len(samples) / wall:,.0f} req/sec "
          f"at concurrency {concurrency}")
    print(f"  decisions     {decisions}")
    if errors:
        print(f"  ERRORS        {errors}")

    print()
    print(LINE)
    print("3. AGAINST THE BUDGET")
    print(LINE)
    print()
    print(f"  budget      {BUDGET_MS:>8.1f} ms")
    print(f"  p50         {client.p50_ms:>8.2f} ms")
    print(f"  p95         {client.p95_ms:>8.2f} ms")
    print(f"  p99         {client.p99_ms:>8.2f} ms")
    print(f"  max         {client.max_ms:>8.2f} ms")
    print()
    if client.p99_ms < BUDGET_MS:
        print(f"  PASS at p99 over HTTP.")
    elif client.p95_ms < BUDGET_MS:
        print(f"  PASS at p95, fails at p99.")
    else:
        print(f"  FAILS the budget over HTTP.")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / "task20_http_latency.json"
    out.write_text(json.dumps({
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "host": host,
        "n": len(samples),
        "concurrency": concurrency,
        "budget_ms": BUDGET_MS,
        "client": client.to_dict(),
        "server": server.to_dict() if server.n else None,
        "wall_seconds": wall,
        "throughput_per_sec": len(samples) / wall if wall else 0,
        "decisions": decisions,
        "errors": errors,
    }, indent=2), encoding="utf-8")
    print()
    print(f"  saved: {out}")
    print(LINE)


if __name__ == "__main__":
    app()