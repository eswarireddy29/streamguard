"""
scripts/load_test.py

Task 31 - where does it break?

Task 20 measured 1 and 4 concurrent clients and both were clean. That
tells you the service works; it does not tell you its capacity. This
raises concurrency step by step until throughput stops improving or
latency breaches the budget, and reports WHERE that happens.

A capacity number nobody has measured is a guess, and the record says
guesses are not acceptable here.

    uvicorn streamguard.api.main:app --port 8000   (terminal 1)
    python scripts/load_test.py                     (terminal 2)
    python scripts/load_test.py --levels 1,2,4,8,16,32
"""

from __future__ import annotations

import json
import statistics
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import typer

from streamguard.eventlog.consumer import FileEventConsumer
from streamguard.ml.splitter import PROJECT_ROOT
from streamguard.utils.logging_config import get_logger, setup_logging

app = typer.Typer(add_completion=False)
log = get_logger(__name__)

REPORTS_DIR = PROJECT_ROOT / "reports"
LINE = "=" * 72
BUDGET_MS = 100.0

_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
urllib.request.install_opener(_opener)

ALLOWED = {
    "transaction_ref", "occurred_at", "card_ref", "customer_ref",
    "merchant_ref", "amount", "currency", "channel", "entry_mode",
    "device_ref", "device_type", "card_type", "city", "country",
    "lat", "lon", "home_city", "home_country", "home_lat", "home_lon",
    "mcc", "merchant_category", "merchant_is_online", "merchant_city",
    "merchant_country",
}


def call(url, body, token=None, method="POST"):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, method=method,
                                 headers=headers)
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            payload = json.loads(r.read().decode())
        return (time.perf_counter() - t0) * 1000, payload, None
    except urllib.error.HTTPError as e:
        return (time.perf_counter() - t0) * 1000, None, f"HTTP {e.code}"
    except Exception as e:
        return (time.perf_counter() - t0) * 1000, None, type(e).__name__


def pct(values, q):
    if not values:
        return 0.0
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round(q / 100 * (len(s) - 1)))))
    return s[k]


@app.command()
def main(
    host: str = typer.Option("http://127.0.0.1:8000"),
    levels: str = typer.Option("1,2,4,8,16",
                               help="Concurrency levels to try"),
    per_level: int = typer.Option(300, help="Requests at each level"),
    skip: int = typer.Option(200_000,
                             help="Match the server's warm offset"),
) -> None:
    setup_logging()
    print(LINE)
    print("TASK 31 - LOAD TEST")
    print(LINE)

    _, auth, err = call(f"{host}/auth/token",
                        {"username": "payment-switch",
                         "password": "switch-dev-password"})
    if err or not auth:
        print(f"\n  ERROR: login failed ({err}). Is the API running?")
        raise typer.Exit(1)
    token = auth["access_token"]

    _, manager, _ = call(f"{host}/auth/token",
                         {"username": "manager",
                          "password": "manager-dev-password"})
    mtoken = manager["access_token"] if manager else None

    concurrency_levels = [int(x) for x in levels.split(",")]
    total_needed = per_level * len(concurrency_levels) + 50

    print()
    print(f"  host         {host}")
    print(f"  levels       {concurrency_levels}")
    print(f"  per level    {per_level}")
    print(f"  budget       {BUDGET_MS:.0f} ms at p99")
    print()
    print("  Each level uses UNIQUE transaction_refs, or the Task 19")
    print("  idempotency cache would return cached results and this")
    print("  would measure a dict lookup (learned at Task 20).")

    # ---- build request bodies -------------------------------------------
    run_id = int(time.time()) % 1_000_000
    consumer = FileEventConsumer(PROJECT_ROOT / "data" / "events",
                                 topic="transactions",
                                 group=f"load_{run_id}", from_beginning=True)
    bodies = []
    seen = 0
    for ev in consumer.stream():
        seen += 1
        if seen <= skip:
            continue
        p = {k: v for k, v in ev.payload.items() if k in ALLOWED}
        p["transaction_ref"] = f"LOAD{run_id}{seen:09d}"
        bodies.append(p)
        if len(bodies) >= total_needed:
            break

    print(f"  prepared     {len(bodies):,} requests")

    # Warm the connection and the JIT paths.
    for b in bodies[:20]:
        call(f"{host}/score", b, token)

    # ---- the sweep --------------------------------------------------------
    print()
    print(LINE)
    print("CONCURRENCY SWEEP")
    print(LINE)
    print()
    print(f"  {'clients':>8}{'req/sec':>10}{'p50':>9}{'p95':>9}"
          f"{'p99':>9}{'max':>9}{'errors':>8}")
    print("  " + "-" * 62)

    results = []
    cursor = 20
    url = f"{host}/score"

    for n in concurrency_levels:
        batch = bodies[cursor:cursor + per_level]
        cursor += per_level
        if len(batch) < per_level:
            print(f"  ran out of prepared requests at level {n}")
            break

        latencies, errors = [], {}
        t0 = time.perf_counter()

        if n == 1:
            for b in batch:
                ms, _, e = call(url, b, token)
                latencies.append(ms)
                if e:
                    errors[e] = errors.get(e, 0) + 1
        else:
            with ThreadPoolExecutor(max_workers=n) as pool:
                for ms, _, e in pool.map(lambda b: call(url, b, token), batch):
                    latencies.append(ms)
                    if e:
                        errors[e] = errors.get(e, 0) + 1

        wall = time.perf_counter() - t0
        throughput = len(batch) / wall if wall else 0
        row = {
            "clients": n,
            "requests": len(batch),
            "wall_seconds": wall,
            "throughput": throughput,
            "p50": pct(latencies, 50),
            "p95": pct(latencies, 95),
            "p99": pct(latencies, 99),
            "max": max(latencies) if latencies else 0,
            "mean": statistics.fmean(latencies) if latencies else 0,
            "errors": errors,
            "n_errors": sum(errors.values()),
        }
        results.append(row)

        print(f"  {n:>8}{throughput:>10.0f}{row['p50']:>9.1f}"
              f"{row['p95']:>9.1f}{row['p99']:>9.1f}{row['max']:>9.1f}"
              f"{row['n_errors']:>8}")

    # ---- where does it saturate? -------------------------------------------
    print()
    print(LINE)
    print("CAPACITY")
    print(LINE)
    print()

    best = max(results, key=lambda r: r["throughput"])
    within_budget = [r for r in results if r["p99"] < BUDGET_MS]

    print(f"  peak throughput    {best['throughput']:.0f} req/sec "
          f"at {best['clients']} clients")
    if within_budget:
        last_ok = max(within_budget, key=lambda r: r["clients"])
        print(f"  within budget to   {last_ok['clients']} clients "
              f"(p99 {last_ok['p99']:.1f} ms)")
    else:
        print(f"  NO level met the {BUDGET_MS:.0f} ms p99 budget")

    breached = [r for r in results if r["p99"] >= BUDGET_MS]
    if breached:
        first = min(breached, key=lambda r: r["clients"])
        print(f"  budget breached at {first['clients']} clients "
              f"(p99 {first['p99']:.1f} ms)")

    # Scaling efficiency: how much of the extra concurrency became
    # throughput. Anything well under 1.0 means requests are queueing.
    if len(results) > 1:
        base = results[0]
        print()
        print("  scaling efficiency (throughput gain / client gain):")
        for r in results[1:]:
            gain = r["throughput"] / base["throughput"] if base["throughput"] else 0
            ideal = r["clients"] / base["clients"]
            print(f"    {r['clients']:>3} clients: {gain:.2f}x of "
                  f"{ideal:.0f}x ideal  ({100 * gain / ideal:.0f}% efficient)")
        print()
        print("  Sub-linear scaling is expected: /score is synchronous")
        print("  CPU work in one uvicorn worker, so the GIL serialises")
        print("  it. Workers cannot be added without losing the shared")
        print("  in-memory feature state (the Task 19 Option A cost).")

    # ---- what the service says about itself ---------------------------------
    if mtoken:
        print()
        print(LINE)
        print("SERVICE METRICS (from /metrics)")
        print(LINE)
        _, snap, err = call(f"{host}/metrics", None, mtoken, method="GET")
        if snap:
            lat = snap["latency_ms"]
            print()
            print(f"  {'stage':<12}{'n':>8}{'p50':>9}{'p95':>9}{'p99':>9}")
            print("  " + "-" * 47)
            for stage in ("total", "features", "graph", "predict", "shap"):
                p = lat[stage]
                if p["n"]:
                    print(f"  {stage:<12}{p['n']:>8,}{p['p50']:>9.2f}"
                          f"{p['p95']:>9.2f}{p['p99']:>9.2f}")
            print()
            print(f"  decisions      {snap['decisions']['counts']}")
            print(f"  flagged        {snap['decisions']['flagged_pct']}%")
            print(f"  errors         {snap['errors']['total']} "
                  f"(rate {snap['errors']['rate']})")
            print(f"  max in flight  {snap['saturation']['max_in_flight']}")
            print(f"  duplicates     {snap['saturation']['duplicates_rejected']}")
            print()
            print("  These are the SERVER's own numbers, measured inside")
            print("  the request. The sweep above is what a CLIENT sees -")
            print("  the difference is HTTP and framework overhead.")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / "task31_load.json"
    out.write_text(json.dumps({
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "budget_ms": BUDGET_MS,
        "levels": results,
        "peak_throughput": best["throughput"],
        "peak_at_clients": best["clients"],
    }, indent=2, default=float), encoding="utf-8")

    print()
    print(LINE)
    print(f"  saved: {out}")
    print(LINE)


if __name__ == "__main__":
    app()