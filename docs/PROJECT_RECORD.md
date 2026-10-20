# STREAMGUARD — PROJECT HANDOFF RECORD

**Last updated:** 19 Oct 2026
Tasks 12–14 complete. Starting Task 15.

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
12. ✅Train/test split by **time** (never random) + baseline model
13. ✅LightGBM training pipeline
14. ✅Class imbalance handling + hyperparameter tuning
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
### Task 12 — Temporal split + baselines ✅ 19 Oct

**Files:** `scripts/inspect_features.py`, `src/streamguard/ml/{__init__,splitter,
metrics,baselines}.py`, `scripts/run_baselines.py`, `tests/test_splitter.py`

**The split.** Days 1–63 train / 64–76 validation / 77–90 test, by **IST
calendar day**, never random. Local midnight, not UTC — a UTC boundary
puts 00:00–05:30 IST into the previous day, the same +5:30 displacement
that hit the Task 6 generator.

**Nuance worth defending:** a temporal split does NOT remove a card from
both sides, and should not. In production you routinely score cards you
have seen before. What the split removes is *future information* about
that card.

**No purging.** Purging (dropping rows at a block boundary) is needed
when a feature looks forward. Task 10 proved every feature looks
strictly backwards, so purging here would be cargo cult.

**Sealed test set.** `split()` returns train and val only. Test requires
`load_test(reason=...)` with a written reason, which appends to
`data/processed/test_set_access.log`. It does not block access — it
makes the access count visible. A test estimate is only honest while
untouched.

**Metrics.** PR-AUC is the headline; a random model scores exactly the
prevalence, so every result prints `lift_over_random` beside it.
precision@k is operational (analysts review ~100/day, k = 100 × days).
ROC-AUC reported, never judged by. Accuracy computed once to prove it
is useless: 99.56% while catching zero fraud.

**Structural guards.** `FORBIDDEN_AS_FEATURES` raises if a label reaches
the feature contract. `Block` keeps X, y and meta separate, so passing
a label as a feature is not possible by typo. `resolve_column()` fails
loudly with the available column list. float32 features halve memory.

**Final numbers** (post-13.7 data; see Task 13.7 for why these changed):

| block | days | rows | fraud | prevalence |
|---|---|---|---|---|
| train | 0–62  | 552,426 | 2,034 | 0.368% |
| val   | 63–75 | 115,566 |   507 | 0.439% |
| test  | 76–89 | 123,117 |   459 | 0.373% |
| total |       | 791,109 | 3,000 |        |

**Baselines on VALIDATION** (k = 1,300; random PR-AUC = 0.0044):

| model | PR-AUC | lift | ROC-AUC | prec@k | recall@k |
|---|---|---|---|---|---|
| always_negative | 0.0044 | 1.0× | 0.5000 | n/a | n/a |
| rules | 0.0045 | 1.0× | 0.5062 | 0.0085 | 0.0217 |
| logistic_regression | 0.7062 | 161.0× | 0.9564 | 0.3023 | 0.7751 |

`always_negative` is degenerate (identical scores); quote prec@k as n/a.

**The rules baseline is a real finding, not a broken implementation.**
On honest data it reaches 1.0× lift — no better than random. The
velocity rule (>5 txns/5min) caught ZERO: `txn_count_5m` averages 1.868
for card testing, so the threshold almost never fires. The speed rule
caught 5. The ratio rule caught 5 of 779 flagged. **Pre-ML rule systems
are close to useless against patterns that do not announce themselves —
half the argument for ML.**

**precision@k ceiling:** only 507 frauds exist in the block, so
precision@1300 cannot exceed 507/1300 = 0.3900.

### Task 13 — LightGBM ✅ 19 Oct

**Files:** `src/streamguard/ml/lgbm.py`, `scripts/train_lgbm.py`,
`scripts/inspect_model.py`

**Settings and why.** `is_unbalance=True` (LightGBM's class_weight
equivalent) prevents the degenerate "never fraud" solution at 0.368%
prevalence — **cost: probabilities are NOT calibrated and read too
high.** Ranking metrics unaffected; calibration is Task 15.
`num_leaves=31`, `min_child_samples=100`: with only 2,034 training
frauds, a leaf of three specific frauds would be memorisation.
`n_jobs=6` of 12 threads — all 12 on 552k × 49 risks paging on 8 GB.
Early stopping on validation **PR-AUC**, not log-loss: stop on the
metric you judge by. Model saved as LightGBM text, not pickle — a
pickle breaks silently across versions and executes code on load.

**Result on VALIDATION** (1,399 of 2,000 trees, stopped early, 239s):

| model | PR-AUC | lift | ROC-AUC | prec@k | recall@k |
|---|---|---|---|---|---|
| always_negative | 0.0044 | 1.0× | 0.5000 | n/a | n/a |
| rules | 0.0045 | 1.0× | 0.5062 | 0.0085 | 0.0217 |
| logistic_regression | 0.7062 | 161.0× | 0.9564 | 0.3023 | 0.7751 |
| **lightgbm** | **0.9201** | **209.7×** | 0.9872 | **0.3638** | **0.9329** |

**Per-pattern recall in the top 1,300 — where trees actually win:**

| pattern | logistic | lightgbm | n |
|---|---|---|---|
| card_not_present | 100.0% | 100.0% | 52 |
| card_testing | 90.2% | 98.8% | 254 |
| geo_impossible | 70.6% | **94.1%** | 17 |
| account_takeover | 52.3% | **83.9%** | 155 |
| merchant_collusion | 65.5% | **82.8%** | 29 |

**TASK 10 OPEN ITEM CLOSED.** Account takeover was the recorded weakest
pattern (best single-feature separation 1.95×), with a decision to
measure before adding features. Linear reaches 52.3%; trees reach
83.9%. The Task 10 note predicted "trees may find interactions a
mean-ratio comparison cannot see" — a 31-point lift is that prediction
confirmed. **No targeted features needed.**

**Why trees beat linear on geo_impossible.** `implied_speed_kmh` is
non-monotonic with respect to fraud: card testing (half of all fraud)
runs at near-zero speed, geo_impossible at thousands of km/h. A linear
model picks ONE direction per feature and so ranks geo_impossible
against itself. A tree splits `speed < 1` and `speed > 900` into
separate leaves. 70.6% → 94.1%. *Caveat: n=17, so one fraud is worth
5.9 points — read as direction, not a precise figure.*

**Feature importance (gain).** Top three are the three signals the
generator was designed around:

| feature | gain | note |
|---|---|---|
| txn_count_5m | 32.39% | card-testing velocity |
| is_manual_entry | 22.84% | card-not-present, definitional |
| distance_from_home_km | 22.40% | geo_impossible |
| merchant_amount_mean | 7.44% | merchant aggregates — the Task 10 design intent for collusion |
| merchant_is_online | 4.71% | |
| is_new_device | 0.61% | rank 9 — **was 58.65% before the 13.7 fix** |
| merchant_txn_count | 0.26% | rank 16 |

Top 5 features = 89.8% of gain; 3 of 49 never split on.

**COLLUSION SHORTCUT — LOW RISK.** `merchant_txn_count` ranks 16 at
0.26% of gain, so the model is not leaning on merchant volume. Gain
importance splits credit between correlated features, so SHAP at Task
18 is still the real check, but the Task 10 worry is not confirmed.

**Overfitting: gap 0.0799** (train 1.0000, val 0.9201). Train PR-AUC
hits 1.0 by iteration 400, then 1,000 more trees buy 0.009 of
validation gain. **Task 14 tuning target: lower `num_leaves`, raise
`min_child_samples`.** The script's "gap is modest" message is
borderline at this level — do not take it at face value.

---

### Task 13.7 — THE GENERATOR LEAK (the most important thing in Phase D)

**How it was found.** The v1 model scored PR-AUC 0.9932 and feature
importance showed `is_new_device` carrying **58.65% of total gain** —
a feature Task 10 had recorded as the WEAKEST signal in the project
(1.95× separation) and which Task 12.5b did not place in the top 15
single features. Three facts that could not all be true.

**Root cause.** Four of five patterns passed `device_ref=None` to
`_build()`. The feature engine reads a missing device as "a device this
card has never used", so `is_new_device = 1.0000` on EVERY row of
card_testing, card_not_present, geo_impossible and merchant_collusion,
against 0.079 for normal traffic. The generator was marking its own
fraud. Worse, account_takeover — the one pattern where a new device is
genuinely the signal — was the only one with a realistic value (0.148).
**The generator had it exactly inverted, because of a missing value,
not a wrong one.**

**Second leak, found by the same audit.** `distance_from_home_km` was
exactly 0.0000 on all card_testing rows (1 unique value vs 539,907 for
normal), because `_card_testing` used the customer's exact home
coordinates with no jitter. And `_pick_merchant` draws uniformly across
the whole country while normal traffic uses distance decay — so
account_takeover sat at a median 925 km from home against normal's 2.3
km, with even its 10th percentile above normal's 99th.

**Third bug, pre-existing and silent.** 62.6% of card_not_present rows
had `seconds_since_prev = 0`: the `t = t + timedelta(...)` line was
missing from the CNP loop, so every transaction in an episode shared
one timestamp. Distance divided by zero hit the 99,999 implied-speed
sentinel. Nothing errored. 224 of 368 CNP gaps were exactly zero.

**The fixes.**
- `_pick_device(customer, prob)` — per-episode device choice with
  realistic per-pattern probabilities in `fraud_patterns.py`:
  card_testing 0.25 (card stolen, not the phone — and ONE device for
  the whole burst, which is itself a signal the model must learn),
  CNP 0.45, geo 0.10 (cloned physical card), collusion 0.08 (the
  customer is genuine), ATO 0.80 (the attacker's own device).
- `_pick_merchant_near(customer, pool, max_km)` — rejection sampling so
  fraud merchants are local like normal ones. ATO 60 km, collusion 25 km.
- `_merchant_collusion` now picks the MERCHANT first, then a customer
  near it — a real complicit shop serves local customers.
- card_testing coordinates jittered 4 km instead of pinned to home.
- geo and collusion get a channel mix (85/88% POS) instead of all-POS,
  which had pinned `is_card_present` to 1.0 and `is_ecommerce` to 0.0.
- CNP clock advance restored.

**Before and after:**

| | before | after |
|---|---|---|
| `is_new_device` rank / gain | 1 / 58.65% | 9 / 0.61% |
| `is_new_device`, 4 patterns | 1.0000, 1 unique value | 0.020–0.183, 2 values |
| ATO distance from home (median) | 925 km | 12 km |
| card_testing distance | 0.0000, 1 unique | 2.79 km, 79 values |
| CNP zero-second gaps | 224 of 368 | 0 of 383 |
| CONSTANT audit findings | 18 | 8 (all legitimate) |
| logistic PR-AUC | 0.9247 | **0.7062** |
| lightgbm PR-AUC | 0.9932 | **0.9201** |
| lightgbm − logistic | 0.07 | **0.21** |

**The numbers went DOWN and that is the result.** Before the fix both
models were riding the same giveaway, so trees beat linear by only
0.07. On honest data the gap is 0.21 — the trees are now earning their
complexity instead of reading a label proxy.

**New tooling (keep these — they are the proof):**
- `scripts/audit_leakage.py` — checks every feature × pattern for
  CONSTANT / DISJOINT / EXTREME. Run after any generator change.
- `scripts/diagnose_baseline.py`, `diagnose_lgbm.py`, `diagnose_geo.py`,
  `diagnose_time.py`
- `tests/test_generator_integrity.py` — 4 tests: no binary feature
  pinned per pattern, fraud episodes advance their clock, collisions
  stay rare, fraud distance overlaps normal. **44 tests passing.**

**The 8 remaining CONSTANT findings are legitimate, and the test has an
explicit allow-list with a reason for each:** `txn_count_1m/5m = 0` for
patterns whose gaps are minutes-to-hours apart is arithmetic, not
leakage; `is_manual_entry = 1` for CNP is the definition of
card-not-present; `merchant_is_online = 0` for collusion is the fixed
six-merchant set, a known Task 10 limitation.

**A trap worth recording:** normal rows carry the STRING `"none"` in
`fraud_type`, not a null. A test filtering with `.notna()` matched all
791k rows and reported 8 "fraud" duplicates that were ordinary Poisson
collisions in normal traffic. Filter on `is_fraud`, not on
`fraud_type.notna()`.

**Interview talking points**

*"My first LightGBM scored 0.9932, which I treated as a leakage suspect
rather than a result. Feature importance showed one feature carrying
58% of gain — a feature my own earlier analysis had recorded as the
weakest signal I had. That contradiction was the thread. It turned out
four of my five fraud patterns passed a null device ID, and my feature
engine read null as 'new device', so the generator was labelling its own
fraud. I fixed the generator, regenerated, and the score fell to 0.9201.
The drop is the deliverable."*

*"The interesting part is what the fix revealed. Before it, LightGBM
beat logistic regression by 0.07 — both were reading the same giveaway.
After it, the gap is 0.21, and account-takeover recall goes from 52% to
84%. The trees are finding real interactions instead of a label proxy."*

*"I also wrote an audit that checks every feature against every fraud
pattern for constant values, and turned it into a test with an explicit
allow-list — each exemption has a written reason. The rule is that a
fraud pattern must SHIFT a feature's distribution, never pin it to a
constant. Pinning is the generator telling the model the answer."*

**HONESTY NOTE FOR README AND REPORT.** 0.9201 describes *my generator*.
Five hand-written patterns encode my assumptions about fraud behaviour,
and the features were designed knowing those patterns. A model that
catches them has learned my patterns, not real-world fraud. Three
separate label proxies were found and fixed; there may be more that
this audit does not detect.

### Task 14 — Imbalance + tuning ✅ 20 Oct

**Files:** `scripts/compare_imbalance.py`, `src/streamguard/ml/tuning.py`,
`scripts/tune_lgbm.py`, `scripts/train_final.py`

#### 14.1 — Four imbalance strategies, measured not assumed

| strategy | PR-AUC | train | gap | prec@k | trees |
|---|---|---|---|---|---|
| **none** | **0.9495** | 0.9953 | **0.0458** | **0.3777** | **116** |
| is_unbalance | 0.9201 | 1.0000 | 0.0799 | 0.3638 | 1399 |
| scale_pos_weight | 0.9201 | 1.0000 | 0.0799 | 0.3638 | 1399 |
| undersample 1:50 | 0.9419 | 0.9999 | 0.0580 | 0.3754 | 294 |

**`is_unbalance=True` was actively hurting.** It had been the default
since Task 13. Removing it gains +0.029 PR-AUC, halves the overfit gap,
and needs 12× fewer trees. At 0.368% prevalence with 2,034 fraud rows,
LightGBM finds the signal without reweighting.

**Side benefit: probabilities are now CALIBRATED.** The "do not quote
these as real chances" caveat carried since Task 12 is gone. Task 15's
calibration curve and Task 16's cost thresholds both need this.

`is_unbalance` and `scale_pos_weight` scored identically to four
decimals — expected, since the former just sets the latter to the class
ratio internally. Confirms both were applied correctly.

Undersampling 1:50 scored 0.9419 on 103,734 rows instead of 552,426.
Not the pick, but worth recording: **81% of the data can be dropped for
0.008 PR-AUC** if Phase E retraining needs to be fast.

#### 14.3 — Random search, 30 trials, 23 minutes

Random rather than grid: six settings × five values = 15,625 fits.
Random search finds near-best combinations in 30–40 tries because
usually only two or three settings matter.

**Selection rule:** highest PR-AUC, but a tie within 0.002 goes to the
smaller gap. Trial 21 (0.9525 / gap 0.0297) beat trial 5 (0.9538 /
0.0387) on that rule. A model likelier to hold up on the sealed test
set is worth 0.0013 of validation PR-AUC.

**Winner:** `num_leaves=31`, `max_depth=10`, `min_child_samples=200`,
`subsample=0.8`, `colsample_bytree=1.0`, `reg_lambda=5.0`

**A real pattern in the search:** `min_child_samples=500` appears in
trials 14, 16, 24, 26 — scoring 0.879, 0.882, 0.883, 0.883, the four
worst results of thirty. 500 rows per leaf is too coarse when only
2,034 frauds exist. Not noise.

#### 14.4 — Final model (`models/lgbm_v4.txt`)

| stage | PR-AUC | gap | trees |
|---|---|---|---|
| Task 13 (is_unbalance=True) | 0.9201 | 0.0799 | 1,399 |
| Task 14.1 (is_unbalance=False) | 0.9495 | 0.0458 | 116 |
| **Task 14.4 (tuned)** | **0.9525** | **0.0297** | **90** |

**Validation** (random PR-AUC 0.0044, lift 217.1×): precision@1300
0.3777 (491 of 507 frauds in the top 1,300), recall@1300 0.9684,
ROC-AUC 0.9976. At threshold 0.5: 392 flagged, **precision 1.0000**,
recall 0.7732.

**Per-pattern recall:** card_not_present 100%, geo_impossible 100%
(n=17), card_testing 99.2%, merchant_collusion 96.6%,
account_takeover 91.6%.

**Importance is now genuinely distributed:** top 5 features hold 71.9%
of gain, down from 89.8% at Task 13. `distinct_merchants_1h` 26.70%,
`is_manual_entry` 16.16%, `distance_from_home_km` 12.21%,
`txn_count_5m` 10.46%. `merchant_txn_count` rank 28 at 0.21% —
collusion shortcut risk stays LOW. 10 of 49 features never split on.

**Interview talking point**

*"I assumed class weighting was necessary at 0.37% prevalence, so I
measured it instead of assuming. Turning it off gained 0.03 PR-AUC,
halved the overfitting gap and cut trees from 1,399 to 90 — and it
restored probability calibration, which the cost-threshold work needs.
Then a 30-trial random search tightened the gap further to 0.0297. My
selection rule breaks ties toward the smaller gap, so the winner scored
0.0013 lower on validation than the top trial but should generalise
better to the test set I have not touched."*

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
**13 of 32 tasks complete.**
### What exists and works right now

| | |
|---|---|
| Database | PostgreSQL 17.11, 9 tables, Alembic migrations applied |
| Data | 791,112 transactions over 90 days, 3,003 fraud (0.380%) across 5 patterns |
| Event log | 791,112 events, 8 segments, offsets + replay verified |
| Stream processor | ~6,700 events/s, 0 errors, resumption across processes verified |
| Features | 49 features, `data/processed/features.parquet`, 140 MB, 0 NaN/inf |
|44 passing — leakage, integrity, split, generator; add rows: Data | 791,109 transactions, 3,000 fraud (0.379%) and Model | LightGBM, val PR-AUC 0.9201 (random 0.0044)

### Task 12 — what comes next
**Verified numbers (19 Oct)**

| block | days | rows | fraud | prevalence |
|---|---|---|---|---|
| train | 0–62  | 552,521 | 2,129 | 0.385% |
| val   | 63–75 | 115,491 |   432 | 0.374% |
| test  | 76–89 | 123,100 |   442 | 0.359% |
| total |       | 791,112 | 3,003 |        |

57 columns = 49 features + 8 metadata. Rows and fraud sum exactly.

**Baselines on VALIDATION** (k = 1,300 = 100 analyst reviews × 13 days;
random PR-AUC = 0.0037):

| model | PR-AUC | lift | ROC-AUC | prec@k | recall@k |
|---|---|---|---|---|---|
| always_negative | 0.0037 | 1.0× | 0.5000 | n/a | n/a |
| rules | 0.0146 | 3.9× | 0.5565 | 0.0408 | 0.1227 |
| logistic_regression | 0.9299 | 248.6× | 0.9981 | 0.3231 | 0.9722 |

`always_negative`'s prec@k and recall@k are **degenerate** — every score is
identical, so argsort returns rows in chronological order, which happened
to contain 3 frauds (chance would give ~4.8). Quote them as n/a. Its
PR-AUC equals prevalence and ROC-AUC is exactly 0.5000, the textbook
values for a model with no information.

`rules` caught ~53 of 432 frauds. Expected: `txn_count_5m` averages 1.841
for card_testing, so a `>5` threshold fires only on the tail of those
bursts; the speed rule can reach at most geo_impossible (25 in this
block); and no rule targets account_takeover at all. **One fraud in eight
is what pre-ML rule systems achieve here — half the argument for ML.**

**Why precision@1300 cannot exceed 0.332:** only 432 frauds exist in the
block. The logistic model's 0.3231 is 97% of that ceiling.

---

#### Task 12.5b — leakage diagnostic (`scripts/diagnose_baseline.py`)

A linear model scoring 0.93 on fraud detection demanded investigation
before being written down. Three checks:

**1. Perfect separators: NONE.** No feature's fraud and normal value
ranges fail to overlap. A leaked label would almost certainly show here.

**2. Ablation decays gracefully, it does not collapse.** Leakage looks
like a cliff — remove the leaked column, score falls to near-random.

| features | PR-AUC | last dropped |
|---|---|---|
| 49 | 0.9299 | — |
| 46 | 0.8894 | distance_from_home_km, distance_from_prev_km, implied_speed_kmh |
| 43 | 0.8798 | distinct_merchants_1h, txn_count_1h, distinct_mccs_1h |
| 40 | 0.8022 | txn_count_5m, is_new_city, merchant_amount_zscore |
| 37 | 0.7585 | txn_count_24h, distinct_cities_24h, is_manual_entry |

With the twelve strongest features gone it still scores 0.7585 = **205×
random**. The signal is distributed, not carried by a giveaway.

**3. Strongest single features (validation, no model fitted):**

| feature | PR-AUC alone | direction |
|---|---|---|
| distance_from_home_km | 0.5476 | low=fraud |
| distance_from_prev_km | 0.4863 | low=fraud |
| implied_speed_kmh | 0.4862 | low=fraud |
| distinct_merchants_1h | 0.4028 | high=fraud |
| txn_count_1h | 0.4019 | high=fraud |
| distinct_mccs_1h | 0.3806 | high=fraud |
| txn_count_5m | 0.3517 | high=fraud |

Seven features each at 95–150× random. A linear combination reaching
0.93 is unremarkable. **Conclusion: not leakage.** The generator produces
fraud that is genuinely separable with the features built for it — which
it should, since the features were designed knowing the patterns. That is
the honest statement, and it belongs in the README.

**A hypothesis that was tested and killed:** `is_manual_entry` was
predicted to be a perfect separator, since Task 10 recorded 1.000 fraud
vs 0.000 normal. It ranks 12th at 0.1190. Task 10's figure was *within
the card_not_present pattern*, which is 50 of 432 frauds. A feature that
perfectly flags 11% of fraud is a weak overall ranker.

---

#### Per-pattern recall in the top 1,300 (logistic, validation)

| pattern | recall | n |
|---|---|---|
| card_not_present | 100.0% | 50 |
| card_testing | 100.0% | 227 |
| account_takeover | 97.7% | 86 |
| merchant_collusion | 88.6% | 44 |
| geo_impossible | 80.0% | 25 |

**OPEN ITEM FROM TASK 10 — CLOSED.** Account takeover was flagged as the
known weakness (best feature separation only 1.95×), with a decision to
measure before adding features. It reaches 97.7% recall. Many weak
signals combined beat one strong signal alone. **No targeted features
needed. Do not add them.**

**NEW FINDING — geo_impossible is the WORST pattern despite having the
STRONGEST single-feature separation (545×).** The cause is in the
direction column above: `implied_speed_kmh` resolves to *low = fraud*,
the opposite of geo_impossible. card_testing is 53% of fraud and runs at
distance ≈ 0 and speed ≈ 0, so the majority pattern sets the feature's
direction. **A linear model can only pick one direction per feature and
cannot represent fraud living at both extremes** — so it ranks
geo_impossible against itself. Same effect on `amount` (low=fraud,
driven by ₹50 card-testing).

> **PREDICTION FOR TASK 13:** LightGBM should lift geo_impossible recall
> well above 80%, because a tree can place `implied_speed < 1` and
> `implied_speed > 900` in separate leaves. If it does not, investigate
> the tree model. This is a better test of Task 13 than watching the
> headline PR-AUC move from 0.93 to 0.95.

*Caveat:* n=25, so one missed fraud moves that recall by 4 points. Read
80% as "about 20 of 25".

**Known limitation of the diagnostic itself:** `single_feature_ap` tries
the feature and its negation and keeps the better score, so it measures
*monotonic ranking power*, not separability. For a feature where fraud
sits at both extremes it reports the majority direction and understates
the feature. `implied_speed_kmh` is more useful to a tree than 0.4862
suggests.

**Interview talking point**

*"My linear baseline scored PR-AUC 0.93, which was high enough that I
treated it as a leakage suspect rather than a result. I ran three checks:
no feature perfectly separated the classes; ablation decayed gracefully
from 0.93 to 0.76 rather than collapsing; and seven features each scored
0.35–0.55 alone, so no single one carried it. Not leakage — my generator
is separable by design, and I say so in the README. The diagnostic also
found something I hadn't predicted: my weakest-separation pattern,
account takeover, hit 97.7% recall, while my strongest, geo-impossible,
was worst at 80%. A linear model has to choose one direction per feature,
and because card testing is half my fraud and runs at near-zero speed,
'low speed' won — so the model ranks the impossible-travel cases against
themselves. That gave me a specific prediction for the tree model to
beat."*

- ~~Account takeover features are weak~~ **CLOSED at Task 12.5b** —
  97.7% recall at k=1,300. No targeted features needed.
- **NEW:** geo_impossible is the weakest pattern (80%, n=25) because
  linear models cannot use a non-monotonic feature. Expect trees to fix
  it at Task 13; verify rather than assume.
- **NEW:** README and report must state that the generator produces
  separable fraud by design, so 0.93 describes the generator, not the
  real world.
- Collusion shortcut risk: `merchant_txn_count` — still open, check at
  Task 18 feature importance. (merchant_collusion 88.6% recall now.)
- psycopg ResourceWarning — still open, fix before Phase E.

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
- ~~Account takeover features weak~~ **CLOSED** — 83.9% recall with trees
  vs 52.3% linear. No targeted features needed.
- ~~Collusion shortcut (`merchant_txn_count`)~~ **LOW RISK** — rank 16,
  0.26% of gain. Confirm with SHAP at Task 18.
- **Overfitting gap 0.0799** — train hits PR-AUC 1.0 by iteration 400.
  Task 14: lower `num_leaves`, raise `min_child_samples`.
- **merchant_collusion distance** mean 258 km vs median 20.5 km — the
  25-try rejection loop occasionally fails for isolated merchants.
  Median is fine; not worth a regeneration.
- **psycopg ResourceWarning** — still open, fix before Phase E.
- **README must state** that 0.9201 describes the generator, not the
  real world, and that three label proxies were found and fixed.

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