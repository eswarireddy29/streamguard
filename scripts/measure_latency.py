"""
scripts/measure_latency.py

Task 20 - p50/p95/p99 for the scoring path, measured in-process.

Measures the SCORER directly, not over HTTP: this isolates the model
and feature cost from network and framework overhead. HTTP adds its
own latency, measured separately in step 3.

    python scripts/measure_latency.py
    python scripts/measure_latency.py --n 5000 --warm-events 100000
"""

from __future__ import annotations

import json
import time
from datetime import datetime

import numpy as np
import pandas as pd
import typer

from streamguard.api.bench import summarize, StageTimer, HEADER, RULE
from streamguard.api.scorer import Scorer, ScorerConfig
from streamguard.eventlog.consumer import FileEventConsumer
from streamguard.ml.splitter import PROJECT_ROOT
from streamguard.utils.logging_config import get_logger, setup_logging

app = typer.Typer(add_completion=False)
log = get_logger(__name__)

REPORTS_DIR = PROJECT_ROOT / "reports"
MODELS_DIR = PROJECT_ROOT / "models"
LINE = "=" * 72

BUDGET_MS = 100.0


@app.command()
def main(
    tag: str = typer.Option("lgbm_v6"),
    n: int = typer.Option(2000, help="Transactions to score"),
    warm_events: int = typer.Option(100_000, help="Events to warm with"),
    skip: int = typer.Option(0, help="Skip this many events before sampling"),
) -> None:
    setup_logging()
    print(LINE)
    print("TASK 20 - LATENCY MEASUREMENT")
    print(LINE)

    model_path = MODELS_DIR / f"{tag}.txt"
    if not model_path.exists():
        print(f"ERROR: {model_path} not found.")
        raise typer.Exit(1)

    print()
    print(f"  model        {model_path.name}")
    print(f"  budget       {BUDGET_MS:.0f} ms (authorisation decision)")
    print(f"  warming with {warm_events:,} events")

    scorer = Scorer(ScorerConfig(model_path=model_path,
                                 warm_events=warm_events))
    scorer.warm()
    print(f"  warmed in    {scorer.warm_seconds:.1f}s")

    # ---- collect transactions to score -----------------------------------
    root = PROJECT_ROOT / "data" / "events"
    consumer = FileEventConsumer(root, topic="transactions",
                                 group=f"bench_{int(time.time())}",
                                 from_beginning=True)
    payloads = []
    seen = 0
    for ev in consumer.stream():
        seen += 1
        if seen <= warm_events + skip:
            continue
        p = dict(ev.payload)
        p.pop("is_fraud", None)
        p.pop("fraud_type", None)
        payloads.append(p)
        if len(payloads) >= n:
            break

    print(f"  scoring      {len(payloads):,} unseen transactions")

    # ---- measure end to end, with stages ---------------------------------
    timer = StageTimer()
    totals, approve_ms, explain_ms = [], [], []
    decisions = {"approve": 0, "review": 0, "block": 0}

    import lightgbm as lgb

    for p in payloads:
        t0 = time.perf_counter()

        t = time.perf_counter()
        base = scorer.computer.process(p)
        timer.record("features", (time.perf_counter() - t) * 1000)

        t = time.perf_counter()
        graph = scorer._graph_process(p)
        timer.record("graph", (time.perf_counter() - t) * 1000)

        merged = {**base, **graph}
        t = time.perf_counter()
        row = np.array([[merged.get(c, 0.0) for c in scorer.feature_names]],
                       dtype=np.float32)
        prob = float(scorer.booster.predict(row)[0])
        timer.record("predict", (time.perf_counter() - t) * 1000)

        if prob >= scorer.cfg.threshold_block:
            d = "block"
        elif prob >= scorer.cfg.threshold_review:
            d = "review"
        else:
            d = "approve"
        decisions[d] += 1

        if d != "approve" and scorer.explainer is not None:
            t = time.perf_counter()
            scorer._explain(row, merged)
            timer.record("shap", (time.perf_counter() - t) * 1000)

        total = (time.perf_counter() - t0) * 1000
        timer.record("total", total)
        totals.append(total)
        (approve_ms if d == "approve" else explain_ms).append(total)

    # ---- report -----------------------------------------------------------
    print()
    print(LINE)
    print("1. BY STAGE")
    print(LINE)
    print()
    print(HEADER)
    print(RULE)
    for s in timer.report():
        print(s.line())

    print()
    print(LINE)
    print("2. BY DECISION PATH")
    print(LINE)
    print()
    print(HEADER)
    print(RULE)
    a = summarize("approve (no SHAP)", approve_ms)
    e = summarize("review/block (SHAP)", explain_ms)
    if a.n:
        print(a.line())
    if e.n:
        print(e.line())
    print()
    print(f"  approve {decisions['approve']:,}   "
          f"review {decisions['review']:,}   block {decisions['block']:,}")
    if a.n and e.n:
        print()
        print(f"  SHAP costs {e.p50_ms - a.p50_ms:.1f} ms at p50 "
              f"({e.p50_ms / a.p50_ms:.1f}x the approve path)")
        print(f"  It runs on {100 * e.n / len(totals):.1f}% of traffic -")
        print("  only what a human will actually look at.")

    # ---- the verdict -------------------------------------------------------
    overall = summarize("end to end", totals)
    print()
    print(LINE)
    print("3. AGAINST THE BUDGET")
    print(LINE)
    print()
    print(f"  budget      {BUDGET_MS:>8.1f} ms")
    print(f"  p50         {overall.p50_ms:>8.2f} ms")
    print(f"  p95         {overall.p95_ms:>8.2f} ms")
    print(f"  p99         {overall.p99_ms:>8.2f} ms")
    print(f"  max         {overall.max_ms:>8.2f} ms")
    print(f"  throughput  {overall.throughput_per_sec:>8,.0f} /sec "
          "(single process, no concurrency)")
    print()
    if overall.p99_ms < BUDGET_MS:
        print(f"  PASS at p99. 99 of 100 requests finish inside "
              f"{BUDGET_MS:.0f} ms.")
    elif overall.p95_ms < BUDGET_MS:
        print(f"  PASS at p95, FAILS at p99. One request in 100 exceeds "
              f"{BUDGET_MS:.0f} ms.")
    else:
        print(f"  FAILS the budget. p95 is {overall.p95_ms:.1f} ms.")
    print()
    print("  Measured in-process: no network, no framework, no")
    print("  concurrency. HTTP adds its own cost - step 3 measures that.")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / "task20_latency.json"
    out.write_text(json.dumps({
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "model": tag,
        "budget_ms": BUDGET_MS,
        "n_scored": len(totals),
        "warm_events": warm_events,
        "decisions": decisions,
        "stages": [s.to_dict() for s in timer.report()],
        "approve_path": a.to_dict(),
        "explain_path": e.to_dict(),
        "overall": overall.to_dict(),
    }, indent=2), encoding="utf-8")
    print()
    print(f"  saved: {out}")
    print(LINE)


if __name__ == "__main__":
    app()