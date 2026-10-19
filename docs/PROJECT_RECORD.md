# STREAMGUARD — PROJECT HANDOFF RECORD

**Last updated:** 19 Oct 2026
**Status:** Phases A, B and C complete (Tasks 1–11). Starting Task 12.

> Paste this whole file into a new chat to resume the project without
> rebuilding context.

---

## WHO I AM

Solo student developer. Budget is exactly **0 rupees** — no paid APIs, no paid
cloud, no paid datasets, no free-trial credits that expire. Everything must run
locally and stay free forever.

I have already built a separate AI Judicial Case Analysis project. This is my
second major project. I want to **understand** every step, not copy code.
Explain things in simple English as if I'm a complete beginner, even when the
technology is advanced.

## HOW I WANT YOU TO WORK WITH ME

Act as my senior software architect, mentor, coding instructor and debugging
partner. Work **one task at a time**. For every step: explain the goal, explain
why, give the exact command and where to run it (Command Prompt / VS Code
terminal / browser), give complete file contents with the exact file path,
explain the important parts, tell me the expected output, give me a way to
verify it worked, then **wait for me to confirm** before moving on.

Do not dump the whole project in one response. Do not invent accuracy scores or
results — help me measure them properly. Do not silently replace a hard feature
with a fake placeholder. Do not make scope decisions for me without asking.

**Terminal vs file rule:** code boxes meant for the terminal are short and start
with `python`, `git`, `pip`, `psql` or `alembic`. Long boxes with prose or `#`
comments are file contents to paste into VS Code, never into the terminal.

---

## MY COMPUTER (verified 18 Oct 2026)

| | |
|---|---|
| OS | Windows 11 Home Single Language 64-bit, Build 26200 |
| Machine | Dell Vostro 3420, BIOS 1.41.0 |
| CPU | Intel Core i5-1235U (12th gen, 12 threads, ~1.3GHz base) |
| RAM | **8 GB — HARD CONSTRAINT.** Page file already heavily used |
| GPU | Intel UHD integrated, 128 MB VRAM → **no usable GPU, no deep learning, no local LLMs** |
| Free disk | 229 GB |
| Admin rights | Yes. Nothing blocked by firewall/antivirus |
| Timezone | Asia/Calcutta (UTC+05:30) |

**Installed:** Python 3.11.0 (in venv), Java 21.0.2, Node v24.16.0, Git 2.54.0,
VS Code 1.141.2, PostgreSQL 17.11
**Deliberately NOT installed:** Docker (too heavy for 8 GB)

Project root: `C:\Users\eshur\projects\streamguard`

---

## THE PROJECT

**Name:** StreamGuard
**Title:** Real-Time Transaction Fraud Detection & Investigation Platform

**Problem:** Card/UPI fraud must be caught in the few hundred milliseconds
between a swipe and the authorisation decision. Batch models that score
overnight are useless. Banks need behavioural features computed *as events
arrive*, a live score, a human-readable explanation for the investigator, and a
feedback loop that learns from the investigator's verdict.

**Users:** fraud analysts (review flagged transactions), risk managers (tune
thresholds, see money impact), ML engineers (monitor drift, retrain).

**What makes it hard (and worth building):**
- Time-windowed features computed online with **no look-ahead leakage**
- Online and offline feature computation must produce identical results
  (training/serving skew is the classic production failure)
- A measured latency budget, not a guessed one
- Cost-sensitive thresholds (a false positive costs real money too)
- Graph features over the card–merchant–device network
- A closed loop: analyst labels flow back into retraining

---

## STACK (all free, all local)

| Layer | Choice |
|---|---|
| Backend | Python 3.11.0, FastAPI, Pydantic, uvicorn |
| Database | PostgreSQL 17.11 |
| Analytics | DuckDB + Parquet (offline feature store) |
| ML | LightGBM, scikit-learn, SHAP, NetworkX — **CPU only** |
| Tracking | MLflow (local file backend) |
| Monitoring | Evidently |
| Frontend | React + Vite + Recharts |
| Testing | pytest |
| Other | Git/GitHub, Alembic, python-dotenv, structlog, typer, Faker |

**Pinned versions:** fastapi 0.115.6, pandas 2.2.3, numpy 1.26.4 (`<2.0`
deliberately), lightgbm 4.5.0, shap 0.46.0, duckdb 1.1.3, sqlalchemy 2.0.36,
psycopg[binary] 3.2.3, mlflow 2.19.0

**Why PostgreSQL 17, not 18.6:** psycopg 3.2.x binary wheels ship PostgreSQL 17
libpq. PG 18 support arrived in psycopg 3.3. Matched the server to the pinned
driver.

**Data:** 100% self-written synthetic generator. No external API, no dataset
download, nothing that can be taken away mid-project.

> **HONESTY RULE:** all accuracy numbers describe *my generator*, not the real
> world. This must be stated plainly in the README and the report.

---

## ARCHITECTURE
Generator/Replay -> Event Log (append-only, ordered, consumer offsets)
  -> Streaming Consumer
  -> Online Feature Engine (velocity, amount z-score, merchant novelty,
     geo-distance - rolling windows)
  -> FastAPI /score -> LightGBM + graph features + SHAP
  -> Decision Engine (approve / review / block, cost-optimised threshold)
  -> PostgreSQL (transactions, decisions, cases, analyst labels, audit)
  -> DuckDB/Parquet offline store -> training -> MLflow -> model registry
  -> React dashboards (live stream, analyst queue, risk KPIs, drift)

**DECIDED at Task 8 — Option A: self-built file-backed event log, NOT Kafka.**
Reason: Kafka's JVM (~1.5–2 GB) plus WSL2 (~1 GB) against 8 GB total, with
PostgreSQL + VS Code + Chrome + React dev server all needed at once in Phase F.
Producer and consumer sit behind abstract base classes, so a Kafka
implementation would be a new subclass, not a rewrite. **This is settled — do
not reopen it.**

---

## TASK LIST

**PHASE A — FOUNDATIONS ✅ COMPLETE**
1. ✅ Environment check, project folder, venv, Git init
2. ✅ Folder structure, dependencies, requirements.txt
3. ✅ Configuration management (.env), logging setup
4. ✅ PostgreSQL install, schema, Alembic migrations (4A + 4B)

**PHASE B — DATA ✅ COMPLETE**
5. ✅ Domain model: customers, cards, merchants, devices
6. ✅ Synthetic generator: realistic normal spending behaviour
7. ✅ Fraud pattern injection + labelled dataset export

**PHASE C — STREAMING**
8. ✅Event log design + producer
9. ✅Consumer with offsets + replay
10.✅Online feature engine (rolling windows, velocity, z-scores)
11.✅ Offline feature store + point-in-time correctness + leakage tests

**PHASE D — MACHINE LEARNING**
12. ⬜**← CURRENT.** Train/test split by **time** (never random) + baseline model
13. ⬜ LightGBM training pipeline
14. ⬜ Class imbalance handling + hyperparameter tuning
15. ⬜ Evaluation: PR-AUC, precision@k, calibration curve
16. ⬜ Cost-based threshold optimisation
17. ⬜ Unsupervised anomaly detector for unseen fraud types
18. ⬜ Graph features (NetworkX) + SHAP + MLflow tracking

**PHASE E — SERVING**
19. ⬜ FastAPI scoring service + request validation
20. ⬜ Latency measurement (p50/p95) + tuning
21. ⬜ Decision engine + business rules layer
22. ⬜ Case management API (analyst queue, verdicts, audit)
23. ⬜ JWT authentication + roles

**PHASE F — FRONTEND**
24. ⬜ React + Vite setup, API client
25. ⬜ Live transaction stream page
26. ⬜ Analyst case queue + investigation view with SHAP
27. ⬜ Risk KPI dashboard + model monitoring page

**PHASE G — QUALITY**
28. ⬜ Unit + integration tests (pytest)
29. ⬜ API tests + error handling hardening
30. ⬜ Drift monitoring (Evidently) + retraining from analyst labels
31. ⬜ Load testing + structured logging + observability

**PHASE H — DELIVERY**
32. ⬜ README, Mermaid diagrams, GitHub + CI, screenshots, demo script,
    project report, slides, interview Q&A

---

## PROGRESS LOG

### Task 1 — Project skeleton ✅ 18 Oct
venv on **Python 3.11.0** (rebuilt twice: 3.13 too new for ML wheels, 3.10
end-of-life). Folder skeleton. `.gitignore`. `git init`.
Branch renamed `master` → `main`.
**Learned:** when VS Code and the terminal disagree about a Python version,
**the terminal is right** — VS Code caches.

### Task 2 — Dependencies ✅ 18 Oct
`requirements.txt` (20 production) + `requirements-dev.txt` (11 dev, includes
`-r requirements.txt`). All pinned with `==`. Verified by import, not by pip
claiming success.
**Rebuild anywhere:** `py -3.11 -m venv .venv` → `.venv\Scripts\activate` →
`pip install -r requirements-dev.txt`

### Task 3 — Config & logging ✅ 18 Oct
- `src/streamguard/config/settings.py` — pydantic-settings reads `.env`,
  validates (`fraud_rate` must be `0 < x < 1`), derives `database_url` and all
  paths from `PROJECT_ROOT`
- `src/streamguard/utils/logging_config.py` — structlog, console or JSON via one
  `.env` setting
- `scripts/check_config.py` — verifies both
- **`.env` confirmed gitignored.** DB password: `StreamGuard2026`

**Standard imports used everywhere since:**
```python
from streamguard.config.settings import settings
from streamguard.utils.logging_config import get_logger, setup_logging
```

### Task 4A — PostgreSQL connection ✅ 18 Oct
PostgreSQL 17.11 installed. `streamguard` database created.
`C:\Program Files\PostgreSQL\17\bin` on **User** PATH (System PATH needs admin
and was greyed out — User PATH works identically).
- `src/streamguard/db/session.py` — engine with pool (size 5, `pool_pre_ping`),
  `get_session()` context manager: commits on success, **rolls back on any
  exception**, always closes
- `scripts/check_db.py` — passes end to end

### Task 4B — Schema & migrations ✅ 18 Oct
- `src/streamguard/db/base.py` — `Base` + naming convention (prevents Alembic
  guessing constraint names) + `TimestampMixin`
- `src/streamguard/db/models.py` — **8 tables:** customers, cards, merchants,
  devices, transactions, decisions, cases, case_events
- Alembic initialised. Migration `302c58b14036` applied. 9 tables live.
- **`alembic.ini` `sqlalchemy.url` left BLANK** — injected from settings in
  `env.py` so the password never reaches GitHub

**Six design decisions to defend in an interview:**
1. `Numeric(12,2)` for money, never `Float` — float can't represent 0.10 exactly
2. `occurred_at` (when it happened) vs `ingested_at` (when we stored it) —
   **every feature must use `occurred_at`** or you leak the future
3. Composite indexes `ix_txn_card_time (card_id, occurred_at)` — the feature
   engine runs that query on every transaction
4. `decisions` separate from `transactions` — a transaction is a **fact**, a
   decision is an **opinion**; retraining produces new opinions about old facts
   without rewriting history
5. `features` stored as JSONB on each decision — lets you detect training/serving
   skew later. You can only detect it if you recorded it
6. `last_four` only, never a card number — even for synthetic data

### Task 5 — Population ✅ 18 Oct
- `src/streamguard/utils/geo.py` — haversine + `implied_speed_kmh`
  (Mumbai→Delhi = 1148 km verified against reality; in 11 min = 6262 km/h)
- `src/streamguard/generator/reference_data.py` — 20 domestic + 6 foreign
  cities, 22 MCC categories, 6 device types. Frozen dataclasses, real MCC codes
- `src/streamguard/generator/entities.py` — `PopulationGenerator`, seeded numpy
  + Faker
- `src/streamguard/generator/loader.py` — `ReferenceLoader`, batch 2000,
  `TRUNCATE ... RESTART IDENTITY CASCADE`, builds ref→id maps
- `scripts/generate_population.py` — typer CLI (`--customers --merchants --seed`)

**DB state:** customers 5,000 / cards 7,532 / merchants 800 / devices 8,463

**Verified by SQL:** 0 cards issued before account opened; spend median 28,117 →
max 406,613 (genuine long tail); Mumbai 800 > Delhi 750 > … > Ahmedabad 246;
Gaming highest risk 0.452

**Leakage prevention (deliberate):**
- `owner_ref` and `is_personal` **not persisted** — in a real payment system
  nobody hands you a table saying which phone belongs to whom; you infer it
- Behaviour knobs (`night_owl`, `travel_propensity`, `category_affinity`,
  `txns_per_day`) live **only in the generator's memory**, never in the DB.
  Task 6 rebuilds the population with the same seed to get them back
- `merchants.risk_score` is generator ground truth — the model must **learn**
  category risk from MCC alone

### Task 6 — Transaction generator ✅ 18 Oct
- `src/streamguard/generator/patterns.py` — hourly profiles per MCC, day-of-week
  multipliers, lognormal amounts, `_round_like_a_human`, distance decay
- `src/streamguard/generator/transactions.py` — `TransactionGenerator`,
  **streams day by day** so memory stays flat
- `src/streamguard/generator/txn_loader.py` — batch 5000, **`ANALYZE` after load**
  (otherwise the planner ignores the composite indexes)
- `scripts/generate_transactions.py` — typer CLI (`--days --seed --no-truncate`)
### Task 7 — Fraud injection ✅ 18 Oct
- `src/streamguard/generator/fraud_patterns.py` — five `FraudPatternSpec`
  definitions, shares summing to 1.0, validated at import time
- `src/streamguard/generator/fraud_injector.py` — `FraudInjector`, third
  independent RNG stream (`seed + 2_000_029`)
- `scripts/generate_transactions.py` — rewritten to merge fraud into each day
### Task 8 — Event log ✅ 19 Oct
**DECISION: Option A — self-built file-backed log, not Kafka.**
Reason: Kafka's JVM (~1.5–2 GB) plus WSL2 (~1 GB) against 8 GB total, with
PostgreSQL + VS Code + Chrome + React dev server all needed simultaneously by
Phase F. Producer and consumer sit behind abstract base classes so a Kafka
implementation is a new subclass, not a rewrite.

- `src/streamguard/eventlog/event.py` — frozen `Event` dataclass, JSON Lines
  serialisation, `schema_version`, `occurred_at` vs `produced_at`
- `src/streamguard/eventlog/producer.py` — `EventProducer` (ABC) +
  `FileEventProducer`. Segmented at 100k events, zero-padded filenames,
  metadata rebuildable from the segments themselves
- `src/streamguard/eventlog/consumer.py` — `EventConsumer` (ABC) +
  `FileEventConsumer`. Per-group offset files, `seek()`, `stream()`, `lag()`
- `src/streamguard/eventlog/txn_source.py` — server-side cursor, strictly
  ordered by `(occurred_at, id)`
- `scripts/load_event_log.py`, `scripts/verify_log.py`

**Log state:** 791,112 events, 8 segments, `data/events/transactions/`
(gitignored — regenerable)

**Key concepts to defend in an interview:**
- **At-least-once delivery.** Offsets are committed *after* processing, so a
  crash causes reprocessing, never loss. Consumers must be idempotent.
  Chosen because duplicate feature computation is harmless; a missed
  transaction is a missed fraud.
- **Producer owns offsets.** Callers never supply one — that is what
  guarantees they are unique and strictly increasing.
- **Metadata is a cache, not the truth.** Delete `metadata.json` and the
  producer recovers its position by counting lines in the segments.
- **Zero-padded segment names.** `000002.jsonl` not `2.jsonl`, or alphabetical
  sorting gives 0, 1, 10, 11, 2 and the consumer reads segments out of order.
- **`lag()`** = log end − committed position. The health metric for any
  streaming consumer; goes on the Task 27 dashboard.

> **LEAKAGE RISK, DELIBERATE AND DOCUMENTED:** the event payload carries
> `is_fraud` and `fraud_type`. A production stream would not — that is what
> you are predicting. They are included because training needs ground truth
> and a parallel label store is more complexity than it is worth here.
> **HARD RULE: the feature engine and scoring path must never read them.**
> To be enforced by a test in Task 11.
>
> `merchants.risk_score` is deliberately **excluded** from the payload — it is
> generator ground truth, and the model must learn category risk from the MCC.

> **Environment incident (19 Oct):** `ModuleNotFoundError: No module named
> 'pydantic_core._pydantic_core'`. Cause: venv site-packages built for 3.11
> being run by a 3.10 interpreter — compiled extensions are version-specific.
> Fixed by rebuilding the venv with `py -3.11` and reinstalling.
> Nothing was lost: code, database and Git history were untouched, which is
> exactly why `requirements.txt` exists and `.venv/` is gitignored.

### Task 9 — Stream processor ✅ 19 Oct
- `src/streamguard/eventlog/handlers.py` — `EventHandler` ABC with
  `handle()`, `on_start()`, `on_stop()`; `_handle_timed()` catches, counts and
  times. Built-ins: `CountingHandler`, `OrderCheckHandler`, `SamplingHandler`
- `src/streamguard/eventlog/metrics.py` — `ProcessorMetrics`: lag, overall vs
  recent rate, error rate, ETA
- `src/streamguard/eventlog/processor.py` — `StreamProcessor` with
  `ProcessorConfig`, chained `register()`, signal handling
- `scripts/run_processor.py`, `scripts/test_handlers.py`

**Full run:** 791,112 processed, 0 failed, 0 order violations, 80.2s,
~9,900/s overall, final lag 0.

**Resumption verified:** run 1 (offsets 0–99,999, 100,000 events) then run 2
(offsets 100,000–791,111, 691,112 events). 100,000 + 691,112 = 791,112 exactly
— no gap, no overlap, across separate processes.

**Design decisions to defend:**
- **Handlers are a chain, not one function** — testable alone, isolated from
  each other's failures, composable. Task 10 and Task 19 plug in without
  touching the processor.
- **Error policy:** log + count + continue, stop only if the error *rate*
  exceeds 1% after a 1,000-event grace period. One bad event is noise; a
  thousand is a symptom. A grace period is needed or 1 failure in the first
  2 events reads as a 50% error rate.
- **Checkpoint on count OR time, whichever first.** Count bounds reprocessing
  after a crash; the time bound stops a slow stream sitting un-committed.
- **`finally` guarantees commit + `on_stop()`.** Most important block in the
  file — a handler that buffers writes loses its final partial batch without it.
- **Signal handling:** first Ctrl+C finishes the batch and commits; second
  force-quits.
**Known performance characteristic (not a bug):** throughput sawtooths
~24,000/s → ~6,000/s in a regular cycle. Cause: `poll()` seeks by skipping
lines, so reaching offset 150,042 means opening segment 1 and skipping 50,042
lines. Early offsets in a segment are fast, late ones slow. Kafka avoids this
with a byte-offset index. Acceptable here — the consumer is sequential, and
~9,900/s drains the whole log in 80s.

### Task 10 — Online feature engine ✅ 19 Oct
- `src/streamguard/features/stats.py` — Welford's algorithm (verified against
  numpy to 12 digits), `ExponentialMovingAverage`
- `src/streamguard/features/state.py` — `CardState` with a `deque(maxlen=50)`,
  bounded sets, `StateStore`. Memory bounded by ENTITY COUNT, not event count
- `src/streamguard/features/computer.py` — **49 features**, `FEATURE_NAMES` as
  the ordered column contract
- `src/streamguard/features/writer.py` — chunked Parquet, explicit Arrow schema
- `src/streamguard/features/handler.py` — plugs into the Task 9 processor
- `scripts/build_features.py`, `check_features.py`, `test_stats.py`,
  `test_features.py`

**Output:** `data/processed/features.parquet` — 791,112 rows, 140 MB, 16 chunks,
118s, 0 errors, **0 NaN/inf**.
**Max 24h count = 26 vs RECENT_WINDOW = 50** — deque ceiling never binding.

**THE GOVERNING RULE:** a feature at time T uses only events strictly before T.
Enforced structurally: `compute_features()` reads state, `update_state()`
writes it, `process()` is the only place the order is encoded.
**Verified:** 10 txns at Rs 1,000 then one at Rs 50,000 → card mean still
1,000.00, ratio 50× at compute time. No self-leakage.

**Feature separation (fraud vs normal, mean ratio):**

| Pattern | Best feature | Normal | Fraud | Ratio |
|---|---|---|---|---|
| card_testing | txn_count_5m | 0.009 | 1.841 | **203×** |
| geo_impossible | implied_speed_kmh | 7.7 | 4,210 | **545×** |
| merchant_collusion | merchant_amount_zscore | −0.014 | 0.783 | **−55×** |
| card_not_present | is_manual_entry | 0.000 | 1.000 | **inf** |
| account_takeover | is_new_device | 0.072 | 0.140 | 1.95× ⚠ |

> **KNOWN WEAKNESS — account takeover.** No feature reaches 2× separation.
> Diagnosis: `is_new_merchant` is 0.607 for *normal* traffic — with 800
> merchants and ~108 transactions per card, novelty is the default, so it
> carries little information. Amount deviation is drowned by legitimate
> variance (a plane ticket is genuinely 10× a customer's mean).
> **DECISION: proceed to Phase D, measure per-pattern recall in Task 15, then
> add targeted features if warranted.** Adding features before measuring is
> guessing. Trees may find interactions a mean-ratio comparison cannot see.

> **KNOWN ARTEFACT:** `merchant_txn_count` is 82 for collusion merchants vs
> 1,340 normal, because the six colluding merchants are a small fixed set. The
> model may learn "low-volume merchant" rather than "inflated amounts" — a
> shortcut that would not generalise. Check in Task 18 feature importance;
> belongs in the report as a synthetic-data limitation.
### Task 11 — Automated leakage test suite ✅ 19 Oct

**WHY THIS TASK EXISTS.** Leakage is the failure mode that kills ML projects,
and it is *silent*: nothing crashes, and results look BETTER than they should.
Every check before this one required me to run a script, read numbers, and
judge whether they looked right. That works while the project is fresh in my
mind. It stops working three weeks later when I change a feature and do not
remember what the correct value was. A test suite replaces human judgement
with PASS/FAIL in two seconds.

**Files created**
- `pyproject.toml` — project metadata + pytest config in one file
- `tests/conftest.py` — shared fixtures (pytest finds this name automatically)
- `tests/test_no_leakage.py` — 14 tests across 4 classes
- `tests/test_feature_file.py` — 9 integrity tests on the Parquet output

**Result: 23 passed in 2.13s**

---

#### The editable install — a structural fix

`pytest` failed at first with `ModuleNotFoundError: No module named
'streamguard'`. Root cause: pytest did not know `src/` was on the import path.

Rather than patching it with a `pytest.ini`, I fixed it properly:
`pyproject.toml` declares the project, and `pip install -e .` installs it into
the venv in **editable mode** — a link to `src/`, not a copy, so edits take
effect immediately with no reinstall.

`import streamguard` now works from anywhere: tests, scripts, notebooks, and
(in Phase E) the FastAPI service. The `sys.path.insert(0, ...)` line at the
top of older scripts is now redundant, though harmless.

*Verified:* `python -c "import streamguard; print(streamguard.__file__)"` →
`C:\Users\eshur\projects\streamguard\src\streamguard\__init__.py`

---

#### THE DECISIVE TEST

`test_is_fraud_does_not_change_features` is the one that matters most.

Compute features for a transaction with `is_fraud=True`. Then compute them for
the *identical* transaction with `is_fraud=False`, in a fresh `StateStore`.
Assert every one of the 49 features is identical.

**If any feature read the label, the two outputs would differ.** This is direct
proof, not code review. Reading the code and concluding it looks correct is
how leakage survives; constructing a case where leakage would be *visible in a
number* is how you actually find it.

The same proof runs for `fraud_type` across all five patterns.

---

#### Test coverage

| Class | What it guards |
|---|---|
| `TestForbiddenFields` | Labels never influence features. Features still compute when `is_fraud`/`fraud_type` are **absent entirely** — as they are in production, where the label is what you are predicting. `risk_score` confirmed absent from the payload. |
| `TestStateOrdering` | A transaction must not contribute to its own statistics. Amount excluded from its own mean (ratio 50×, not 9×). Current txn excluded from velocity counts. Novelty reflects the past only. `compute_features()` is pure — calling it twice changes nothing. |
| `TestTemporalCorrectness` | A later transaction cannot change an earlier one's features. First-transaction defaults are all defined. Window boundaries count correctly at the edge. |
| `TestDeterminism` | Two computers fed identical events agree exactly (divergence would mean hidden state — dict ordering, an unseeded random draw, a clock read). No NaN or infinity on deliberately awkward inputs. Feature vector order is stable. |

`tests/test_feature_file.py` validates the *output* rather than the logic: all
49 columns present, row count matches the database, `transaction_ref` unique
(a duplicate means an event was processed twice), offsets contiguous 0..N-1,
rows chronological, no NaN/inf, fraud rate within 2× of configured, all five
fraud types present, all amounts positive.

---

#### A test that has never failed cannot be trusted

So I broke it on purpose. In `computer.py`, swapped the two lines in
`process()` so `update_state()` ran *before* `compute_features()` — which
introduces self-leakage.
tests/test_no_leakage.py::TestStateOrdering::test_novelty_reflects_past_only FAILED
assert first[“is_new_merchant”] == 1.0
E assert 0.0 == 1.0

The first-ever visit to a merchant came back as "not new", because
`update_state()` had already recorded it. **Caught in 0.30 seconds.** Restored
the correct order → 23 passed.

Note which test fired: *novelty*, not the ₹50,000 mean test. Novelty breaks on
a single transaction; the mean test needs ten before distortion is visible.
Multiple independent tests catching the same bug from different angles is what
a good suite looks like.

---

#### Design notes

- **A fresh `FeatureComputer` per test**, via fixture. Tests must not affect
  each other — leftover state makes results depend on execution order, which
  produces failures that appear and vanish randomly (*test pollution*).
- **`make_payload()` gives every field a default**, so each test overrides only
  what it cares about and stays focused on one behaviour.
- **The `feature_file` fixture skips** rather than fails when
  `features.parquet` is missing, so the suite still runs on a fresh clone.

#### Commands
pytest # everything (23 tests)
pytest tests/test_no_leakage.py # fast, no feature file needed
pytest -m “not slow” # skip file-based tests
pytest -x # stop at first failure
pytest --tb=long # full error traces

#### Known cosmetic issue

`ResourceWarning: connection ... was deleted while still open` from psycopg
during `test_row_count_matches_database`. Harmless now, but worth fixing before
Phase E — with a connection pool of 5, leaked connections become a hang.

#### Interview talking point

*"I wrote a test that computes features for the same transaction twice — once
labelled fraud, once not — and asserts every feature is identical. If any
feature read the label, they would differ. Then I deliberately inverted the
state-update order to confirm the suite catches self-leakage. It did, in 0.3
seconds."*

**DB state:** 791,112 transactions / 3,003 fraud / **0.380%**

| Pattern | n | Avg amount | Txns per card | Signature |
|---|---|---|---|---|
| card_testing | 1,586 | ₹50 | 13.4 | velocity, trivial amounts |
| account_takeover | 663 | ₹10,391 | 7.4 | deviation from personal baseline |
| card_not_present | 405 | ₹6,934 | 2.6 | channel + category + amount |
| merchant_collusion | 194 | ₹55,136 | 3.8 | merchant-level aggregates |
| geo_impossible | 155 | ₹5,327 | 2.8 | implied speed |

**Design:** fraud generated as **episodes** (a burst on one compromised card),
not isolated rows — that is what creates the velocity and deviation signals.
Six fixed collusion merchants, because collusion is a property of the merchant.

> ### 🐛 TWO BUGS FOUND AND FIXED
> **1. Doubled data.** The old generation loop was left in the script beside
> the new one, so every day was inserted twice — 1,580,292 rows instead of
> ~790k, halving the fraud rate to 0.190%. Caught from the progress output:
> day 1 showed `+8,246` but `total 799,358`, which is impossible for a counter
> starting at zero. **Nothing errored.** Fixed by rewriting the script whole.
>
> **2. Fraud anchored to the wrong window.** `_random_anchor()` used
> `settings.simulation_days` (90) rather than the `n_days` actually being
> generated, so a `--days 7` run discarded 96% of its fraud (238 generated,
> 10 kept). Fixed by passing `n_days` into `generate_episodes()` and
> `_random_anchor()`.

**Honesty note for README and report:** these five patterns encode *my*
assumptions about fraud behaviour. A model that catches them has learned my
patterns, not real-world fraud.

---

## APPENDIX — Task 6 and Task 7 detail (content below belongs to those tasks, not Task 11)
**DB state:** ~788,000 transactions over 90 days, `is_fraud = false` on all of
them (fraud is Task 7)

> ### 🐛 BUG FOUND AND FIXED — timezone displacement
> The generator used `timezone.utc`, so the designed 19:00 evening peak appeared
> at **00:30 IST** — every hour displaced by exactly +5:30.
> **Fix:** `IST = timezone(timedelta(hours=5, minutes=30))` defined in **both**
> `entities.py` and `transactions.py`, used instead of `timezone.utc`.
> **Caught by plotting the data, not by reading the code.**
>
> **RULE from here on:** always query hours as
> `EXTRACT(HOUR FROM occurred_at AT TIME ZONE 'Asia/Kolkata')`. Plain
> `EXTRACT(HOUR ...)` uses the session timezone and gives different answers on
> different machines.

**Verified curve after fix:** trough 04:00 (3,559) → lunch 13:00 (54,347) →
**peak 19:00 (65,206)** → midnight bump 00:00 (12,786, the night owls).
18.3× between quietest and busiest hour.

**Other design points:**
- Separate RNG streams (`seed + 1_000_003`) so changing customer count doesn't
  shift transaction randomness
- Distance cache: 5,000 × 800 floats ≈ 32 MB, avoids 560M repeated haversine calls
- Poisson for daily transaction counts — models "independent events in a fixed
  interval"
- Online transactions use the **customer's** location, not the merchant's

---

## COMMIT HISTORY
Tasks 1-6 commits: f4f9821, e164c0e, bf30d15, 511a694, 2ab5b20, 846daa6,
                   e191598, 0e1cc41
Task 7  — fraud injection with five distinct patterns
Task 8  — append-only event log with producer, consumer and offsets
Task 9  — stream processor with handlers, checkpointing and metrics
Task 10 — online feature engine, 49 features over 791k events
Task 11 — automated leakage and integrity tests, editable install

Run `git log --oneline` for the authoritative list.
---

## COMMANDS THAT WORK

```bash
# Every new terminal, always first
cd C:\Users\eshur\projects\streamguard
.venv\Scripts\activate

# Health checks
python scripts/check_config.py
python scripts/check_db.py

# Regenerate data (population FIRST — cards must exist before transactions)
python scripts/generate_population.py
python scripts/generate_transactions.py
python scripts/generate_transactions.py --days 7     # quick test

# Database
psql -U postgres -d streamguard        # password StreamGuard2026
alembic upgrade head
alembic revision --autogenerate -m "description"
```

---

## KNOWN ISSUES

- None blocking.
- Cosmetic: psql warns `Console code page (437) differs from Windows code page
  (1252)` — only affects accented characters. `chcp 1252` silences it.
- Cosmetic: Git warns `LF will be replaced by CRLF`. A `.gitattributes` with
  `* text=auto eol=lf` would silence it.

---

## WHERE I AM RIGHT NOW

**11 of 32 tasks complete. Phases A, B and C done. Starting TASK 12.**

### What exists and works right now

| | |
|---|---|
| Database | PostgreSQL 17.11, 9 tables, Alembic migrations applied |
| Data | 791,112 transactions over 90 days, 3,003 fraud (0.380%) across 5 patterns |
| Event log | 791,112 events, 8 segments, offsets + replay verified |
| Stream processor | ~6,700 events/s, 0 errors, resumption across processes verified |
| Features | 49 features, `data/processed/features.parquet`, 140 MB, 0 NaN/inf |
| Tests | 23 passing — leakage and integrity |

### Task 12 — what comes next

**Temporal train/test split + baseline models.**

**Why the split must be by TIME, never random.** `train_test_split(X, y,
random_state=42)` is wrong here for two separate reasons:
1. It shuffles time — March rows land in training while February rows are in
   test, so the model reads the future to predict the past. Impossible in
   production.
2. It splits individual cards across both sides — the model memorises a card's
   habits, then is "tested" on a transaction surrounded by ones it learned
   from. That is **group leakage**.

**Correct split:**
- Days 1–63 → training (~70%)
- Days 64–76 → validation (~15%, for tuning)
- Days 77–90 → test (~15%, **touched exactly once**, at Task 15)

**Why a baseline matters.** "PR-AUC 0.72" is meaningless alone. Against a
baseline of 0.21 it is an achievement; against 0.68 the complexity was not
worth it. Three baselines to build:
1. Always predict "not fraud" — scores 99.62% accuracy, catches zero fraud.
   Exists purely to prove accuracy is a useless metric here.
2. Hand-written rules (>5 txns in 5 min, OR speed >900 km/h, OR amount >20×
   card mean) — what banks used before ML. Not a strawman.
3. Logistic regression — if LightGBM barely beats it, the 49 features have no
   useful interactions.

**Metrics to use.** PR-AUC (correct for rare events; a random model scores
0.0038 here, equal to the fraud rate — so context matters enormously when
reading the number). precision@k (if analysts review 100 cases a day, how many
of my top 100 are real fraud?). Per-pattern recall. ROC-AUC reported but not
judged by — it flatters imbalanced data.

**Files to create in Task 12:** `splitter.py`, `baselines.py`, `metrics.py`.

### Remaining roadmap

- **13–18:** LightGBM, imbalance handling, evaluation, **cost-based thresholds**
  (missing fraud costs ₹5,000, blocking a real customer ₹200 — a 25:1
  asymmetry, so the threshold is computed, not defaulted to 0.5),
  unsupervised detection, SHAP + graph features
- **19–23:** FastAPI scoring service, measured latency, decision engine, case
  management, JWT auth
- **24–27:** React dashboard — live stream, case queue, investigation view
  with SHAP, risk KPIs
- **28–31:** tests, drift monitoring, retraining loop, load testing
- **32:** README, diagrams, GitHub, screenshots, report, slides, interview Q&A

### Open items carried forward

- **Account takeover features are weak** (best separation 1.95×). Decision:
  measure per-pattern recall at Task 15 first, then add targeted features if
  warranted. Do not add features before measuring.
- **Collusion shortcut risk:** `merchant_txn_count` is 82 for colluding
  merchants vs 1,340 normal, so the model may learn "low-volume merchant"
  instead of "inflated amounts". Check in Task 18 feature importance.
- **psycopg ResourceWarning** in `test_row_count_matches_database` — harmless
  now, fix before Phase E.

### Three bugs already found — all of them silent

None raised an exception. All were caught by comparing numbers against what
they should have been:
1. **Timezone displacement** — 19:00 peak appeared at 00:30 IST. Caught by
   plotting the hourly histogram.
2. **Doubled data** — 1.58M rows instead of 790k. Caught because day 1 showed
   `+8,246` but `total 799,358`, impossible for a counter starting at zero.
3. **Fraud in the wrong window** — a 7-day run kept 10 of 238 frauds. Caught by
   comparing generated against loaded counts.

**The lesson for Phase D:** in data work the dangerous results do not crash —
they look plausible. If Task 13 reports PR-AUC above 0.95, do not celebrate.
Check for leakage first.