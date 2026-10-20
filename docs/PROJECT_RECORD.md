# STREAMGUARD — PROJECT HANDOFF RECORD

**Last updated:** 20 Oct 2026
**Status:** → Phases A–E complete. Task 25 complete. Starting Task 26.

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
15. ✅ Evaluation: PR-AUC, precision@k, calibration curve
16. ✅Cost-based threshold optimisation
17. ✅Unsupervised anomaly detector for unseen fraud types
18. ✅Graph features (NetworkX) + SHAP + MLflow tracking

**PHASE E — SERVING**
19. ✅FastAPI scoring service + request validation
20. ✅Latency measurement (p50/p95) + tuning
21. ✅ Decision engine + business rules layer
22. ✅Case management API (analyst queue, verdicts, audit)
23. ✅JWT authentication + roles

**PHASE F — FRONTEND**
24. ✅React + Vite setup, API client
25. ✅Live transaction stream page
26. ⬜ **← CURRENT.**Analyst case queue + investigation view with SHAP
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



---

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

### Task 15 — Evaluation + calibration ✅ 20 Oct

**Files:** `src/streamguard/ml/calibration.py`,
`scripts/check_calibration.py`, `scripts/evaluate_test.py`

#### THE HEADLINE NUMBER

**Test PR-AUC 0.9573** on days 77–90 (123,117 rows, 459 fraud, 0.373%
prevalence). Lift over random: **256.8×**. precision@1400 0.3200 (448
of 459 frauds in the top 1,400), recall@1400 0.9760. At threshold 0.5:
357 flagged, **precision 1.0000**, recall 0.7778.

`data/processed/test_set_access.log` contains **exactly one line.** The
test set was opened once, after every decision was final.

| | validation | test |
|---|---|---|
| PR-AUC | 0.9525 | **0.9573** |
| difference | | **−0.0048** |

The two agree within 0.005. **Tuning on validation did not inflate the
estimate** — that is what the sealed test set was for.

**Per-pattern recall on test:**

| pattern | recall | n |
|---|---|---|
| card_not_present | 100.0% | 42 |
| geo_impossible | 100.0% | 35 |
| card_testing | 98.9% | 264 |
| account_takeover | 94.2% | 103 |
| merchant_collusion | 86.7% | 15 |

*merchant_collusion n=15, so one miss is 6.7 points. Read as direction.*

#### 15.2 — Why calibration matters, and the result

Ranking metrics (PR-AUC, precision@k) only care about ORDER. Task 16
computes thresholds from the probability VALUES:
`P(fraud) × ₹5,000` vs `(1 − P(fraud)) × ₹200`. Wrong probabilities
mean a wrong threshold even when the ranking is perfect.

Buckets are **quantile**, not equal-width: at 0.37% prevalence,
equal-width buckets would put 99% of rows in the first one.

**Calibration on TEST:**

| metric | value |
|---|---|
| mean predicted | 0.00336 |
| actual rate | 0.00373 |
| bias | −0.00037 |
| Brier | 0.000635 |
| Brier baseline | 0.003714 |
| improvement | 82.9% |
| ECE | 0.00053 |
| worst bucket | 0.00451 |

**Probabilities are usable as probabilities.** Task 16 computes cost
thresholds directly, with no isotonic or Platt step. This is the payoff
from Task 14.1's `is_unbalance=False` decision.

**The reliability table is also the clearest evidence of generator
separability:** buckets 0–8 hold 110,805 rows and **one** fraud between
them. All 458 remaining frauds are in bucket 9. Real fraud does not
separate like that.

#### Bug found and fixed — `LGBMModel.load()`

`load()` attached a booster to a bare `LGBMClassifier` whose internal
`_n_features` was never set, so `predict_proba()` raised *"Model
n_features_ is -1"*. Written at Task 13 and not caught, because
`inspect_model.py` only reads feature importances and never predicts.
**Any code path that loads a saved model and scores with it was
broken** — which Phase E's FastAPI service would have hit immediately.
Fixed by predicting through the booster directly.

**Interview talking point**

*"I kept days 77–90 sealed from Task 12 onward. `load_test()` required
a written reason and logged every access, so I can prove the test set
was opened once, after the model was final. Validation said 0.9525,
test said 0.9573 — a gap of 0.005, which tells me the hyperparameter
tuning generalised rather than fitting the validation window. The
calibration check also earned its place: ECE 0.0005 means I can compute
cost-based thresholds straight from the probabilities instead of
calibrating first."*

**HONESTY NOTE.** 0.9573 describes the generator. The reliability table
makes the point: 110,805 test rows below bucket 9 contain one fraud
between them. Real card fraud is not that separable. Three generator
label proxies were found and fixed at Task 13.7; there may be more this
audit does not detect.

### Task 16 — Cost-based threshold ✅ 20 Oct

**Files:** `src/streamguard/ml/costs.py`, `scripts/optimize_threshold.py`

**Why 0.5 is the wrong threshold.** It is correct only when a false
positive and a false negative cost the same. Here:

| mistake | cost | why |
|---|---|---|
| missed fraud | ₹5,000 | the money is gone |
| blocked customer | ₹200 | support call, churn risk |
| analyst review | ₹50 | staff time, not money lost |

**25:1 asymmetry** — it is worth blocking ~25 legitimate transactions
to catch one fraud. These are ASSUMPTIONS, not measured figures; a real
bank would take them from chargeback data and churn analysis. They are
stated explicitly so the threshold can be re-run with other numbers.

**The theoretical answer.** Block when the expected cost of approving
exceeds the expected cost of blocking:
exceeds the expected cost of blocking:

    p × FN > (1 − p) × FP   →   p > FP / (FP + FN) = 200/5200 = 0.03846

**The measured optimum is 0.03061** — close to theory, which is itself
a check: the theoretical value depends only on the cost ratio, nothing
about the data. They agree **because the probabilities are calibrated**
(Task 15, ECE 0.00053). Uncalibrated scores would have diverged.

**On VALIDATION:**

| threshold | caught | missed | blocked | precision | recall | cost |
|---|---|---|---|---|---|---|
| 0.50000 (default) | 392 | 115 | 0 | 1.0000 | 0.7732 | ₹575,000 |
| 0.03846 (theory) | 478 | 29 | 202 | 0.7029 | 0.9428 | ₹185,400 |
| **0.03061 (optimum)** | **482** | **25** | **264** | 0.6461 | **0.9507** | **₹177,800** |

**₹397,200 saved vs the default — 69.1% of the cost at 0.5.**

**The cost curve is genuinely U-shaped**, and both ends are ~12× worse
than the optimum:

| threshold | caught | missed | blocked | cost |
|---|---|---|---|---|
| 0.00030 | 503 | 4 | 11,054 | ₹2,230,800 |
| 0.00640 | 495 | 12 | 1,422 | ₹344,400 |
| **0.03061** | **482** | **25** | **264** | **₹177,800** |
| 0.08980 | 460 | 47 | 59 | ₹246,800 |
| 0.98835 | 117 | 390 | 0 | ₹1,950,000 |

**Precision DROPS from 1.0000 to 0.6461 and that is correct.** Those
264 false alarms cost ₹52,800; the 90 extra frauds they catch would
have cost ₹450,000. Optimising precision here would lose money.

#### Three-way decision: approve / review / block

A binary decision throws away the model's uncertainty. Middle scores
are exactly the cases worth analyst time: too risky to approve
silently, not certain enough to block a paying customer.

| band | threshold | rows | fraud | legit |
|---|---|---|---|---|
| block | ≥ 0.03061 | 746 | 482 | 264 |
| review | ≥ 0.01113 | 554 | 9 | — |
| approve | < 0.01113 | 114,266 | 16 missed | — |

**₹160,500 — ₹17,300 cheaper than the binary optimum.** The review band
catches 9 frauds the binary threshold would have approved, for ₹27,700
of analyst time. It also respects capacity: **43 reviews/day against
100 analyst capacity**, so the queue is workable.

**Caveat:** `three_way()` assumes an analyst always judges correctly.
Real analysts do not, so ₹160,500 is a floor, not a forecast.

#### APPLIED TO TEST (threshold chosen on validation, only reported here)

| threshold | caught | missed | blocked | precision | recall | cost |
|---|---|---|---|---|---|---|
| 0.50000 | 357 | 102 | 0 | 1.0000 | 0.7778 | ₹510,000 |
| **0.03061** | **436** | **23** | **253** | 0.6328 | **0.9499** | **₹165,600** |

**₹344,400 saved across 123,117 transactions.** Recall 0.7778 → 0.9499.

The threshold was chosen on validation and **not re-optimised on test**.
`test_set_access.log` now has two lines, both with written reasons:
Task 15's final evaluation and this reporting access.

**Interview talking point**

*"The default threshold of 0.5 assumes a false positive and a false
negative cost the same. In fraud they differ by 25:1, so I computed the
threshold from the cost model instead. Theory says 200/5200 = 0.0385;
the measured optimum on validation was 0.0306, and those agreeing is
itself evidence the probabilities are calibrated, because the
theoretical value depends only on the cost ratio. On the held-out test
set that threshold saved ₹344,400 across 123,000 transactions and
raised recall from 0.78 to 0.95. Precision fell to 0.63 — which is
correct, because the extra false alarms cost ₹52,800 while the frauds
they caught would have cost ₹450,000."*

*"I also built a three-way decision, because a binary cut throws away
the model's uncertainty. Routing the middle band to an analyst was
₹17,300 cheaper again and generated 43 reviews a day against a capacity
of 100 — though that figure assumes analysts are always right, so I
treat it as a floor."*

### Task 17 — Unsupervised anomaly detection ✅ 20 Oct

**Files:** `src/streamguard/ml/anomaly.py`, `scripts/run_anomaly.py`,
`scripts/test_novel_fraud.py`

**The problem.** LightGBM learned five patterns from labels. A sixth
pattern invented next month would score low and be approved — a
supervised model can only catch what it was shown. An unsupervised
detector learns what NORMAL looks like and flags distance from it, so
a new attack is just as anomalous as an old one.

**Two detectors, both fitted on NORMAL TRAINING ROWS ONLY.** Labels
select which rows to train on; they are never a feature. Including
fraud would teach the detector that fraud is normal.

- **Isolation Forest** — random splits isolate outliers faster than
  points in a dense cluster. No distance metric, no distribution
  assumption. Quantile-transformed first, because amounts are lognormal
  and a few huge values would dominate every split.
- **Mahalanobis** — distance from the centre of normal traffic,
  accounting for correlation. Two correlated features moving together
  is ordinary; one moving without the other is anomalous. Ridge term
  (1e-6) added because some features are collinear and the covariance
  matrix would otherwise be singular.

#### 17.2 — On KNOWN fraud (the unfair test)

| model | PR-AUC | lift | prec@k | recall@k |
|---|---|---|---|---|
| isolation_forest | 0.3842 | 87.6× | 0.2038 | 0.5227 |
| mahalanobis | 0.5295 | 120.7× | 0.2346 | 0.6016 |
| lightgbm | 0.9525 | 217.1× | 0.3777 | 0.9684 |

LightGBM wins easily — it trained on exactly these patterns. **But both
detectors are 88–121× random having never seen a label**, so they
learned something real about normal behaviour.

**Per-pattern, the useful split:**

| pattern | isolation | mahalanobis | lightgbm |
|---|---|---|---|
| card_not_present | 3.8% | **100.0%** | 100.0% |
| card_testing | 93.7% | 85.8% | 99.2% |
| geo_impossible | 76.5% | 70.6% | 100.0% |
| merchant_collusion | 20.7% | 27.6% | 96.6% |
| account_takeover | 3.9% | 9.7% | 91.6% |

Patterns that are **statistically weird in isolation** get caught
unsupervised. Patterns that are **contextually** fraudulent but
individually ordinary do not: an account-takeover transaction looks
like a normal purchase, and only its relationship to that customer's
history makes it fraud.

#### 17.3 — THE REAL EXPERIMENT: holdout by pattern

For each pattern, LightGBM was **retrained with that pattern's rows
removed from training**, then measured on it in validation. From the
supervised model's point of view, that pattern is an attack invented
after deployment. The detectors are unchanged — they never used labels,
so there is nothing to remove.

**Recall on the held-out pattern, top 1,300:**

| pattern | n | lightgbm | isolation | mahalanobis |
|---|---|---|---|---|
| card_not_present | 52 | **0.0%** | 3.8% | **100.0%** |
| card_testing | 254 | **0.0%** | **93.7%** | 85.8% |
| account_takeover | 155 | **33.5%** | 3.9% | 9.7% |
| merchant_collusion | 29 | **41.4%** | 20.7% | 27.6% |
| geo_impossible | 17 | 76.5% | 76.5% | 70.6% |

**LightGBM catches ZERO of 254 card-testing frauds and ZERO of 52 CNP
frauds when those patterns are absent from training.** Not "worse" —
zero. An unsupervised detector that never saw a label catches 93.7% and
100% of them.

**This is the measured case for running both in production**, not an
assertion. The two approaches fail on different things:

- supervised fails on patterns it has not seen
- unsupervised fails on patterns that are contextually, not
  statistically, abnormal

**Also measured:** the crippled model's overall PR-AUC drops to 0.4574
when card testing is removed — that pattern is 52% of all fraud, so
losing it halves performance. Removing geo_impossible costs almost
nothing (0.9422), because it is 17 validation rows.

**Caveat on the 100%.** Mahalanobis scores exactly 100% on CNP because
`is_manual_entry` is 1.0 for every CNP row and ~0 for normal traffic —
a documented generator property (Task 13.7A kept it as legitimate: it
IS the definition of card-not-present). Real CNP fraud would not
separate that cleanly.

**Interview talking point**

*"A supervised fraud model can only catch what it was trained on, so I
tested that instead of assuming it. For each of my five patterns I
retrained LightGBM with that pattern deleted from training, then
measured recall on it. On card testing and card-not-present it caught
exactly zero — 0 of 254 and 0 of 52. An unsupervised detector fitted
only on normal traffic, with no labels at all, caught 93.7% and 100% of
the same rows. That is the measured argument for running both: they
fail on different things. The supervised model wins on patterns that
are contextually fraudulent but individually ordinary, like account
takeover, where you need to know the customer's history to see anything
wrong."*

### Task 18 — Graph features + SHAP + MLflow ✅ 20 Oct

**Files:** `src/streamguard/features/graph.py`,
`scripts/build_graph_features.py`, `scripts/train_with_graph.py`,
`src/streamguard/ml/explain.py`, `scripts/explain_model.py`,
`src/streamguard/ml/tracking.py`, `scripts/log_experiments.py`

---

#### 18A — Graph features

**The gap they fill.** The 49 existing features describe ONE transaction
and ONE card's own history. They cannot see that this card and that card
both used the same device last week. Fraud rings share infrastructure,
and that sharing is only visible in the network.

**No look-ahead, structurally.** The graph is built incrementally in
chronological order with the same contract as Task 10: `compute()`
reads, `update()` writes, `process()` is the only place the order is
fixed. A day-10 feature cannot know about day 80.

**`device_ref` was missing from the feature file** — the Task 10 writer
kept only the derived `is_new_device` flag, not the raw id. The graph
needs to know WHICH device, so it is joined back from the database on
`transaction_ref`. Present on 784,041 of 791,109 rows; the 7,068 nulls
are card-present POS transactions with no device, which correctly get
0 for device features.

**Graph size:** 7,295 cards, 8,313 devices, 800 merchants, 49,874
card–device edges, 481,155 card–merchant edges, **3,597 shared devices**.

**Two features dropped as dead:**

- `ring_size` — 36.78 normal vs 36.38 fraud at a cap of 50 (and 156 vs
  162 at a cap of 200). **One hop saturates**: with 7,295 cards sharing
  8,313 devices, the average card touches ~7 devices and each device
  serves ~6 cards, so every card has ~40 neighbours by construction. The
  feature measures connectivity, not rings. **The generator assigns
  devices randomly, so there are no rings to find** — a limitation of
  the synthetic data, not of the approach.
- `ring_fraud_density` — constant 0.0 by design. Filling it from labels
  would be leakage; in production it would come from CONFIRMED analyst
  verdicts, which is a Task 30 input.

**Result: +0.0157 PR-AUC** (0.9518 → 0.9675 on the same validation
block). **merchant_collusion recall 96.6% → 100%** — collusion is a
merchant-level property and these are the first merchant-network
features in the model. Overfit gap unchanged at 0.0276.

**A prediction that failed, and why it is instructive.**
`device_card_velocity_1h` had by far the strongest standalone ratio
(6.44× — 0.0912 normal vs 0.5870 fraud) and was expected to be the key
feature. It ranks **49 of 58 at 0.00% gain** — essentially unused. It is
redundant with `txn_count_1h` and `distinct_merchants_1h`, which the
model already leans on. **A high univariate ratio does not mean a
feature adds anything; the model may already have that information.**

**The useful graph features are the "low = fraud" ones:**
`device_card_count_7d` (rank 9, 2.23%), `device_card_count` (rank 10,
1.77%), `merchant_card_count_7d` (rank 14, 1.16%) — all with ratios
BELOW 1.0. Fraud happens on low-traffic devices and low-volume
merchants. Graph features hold 5.69% of total gain.

---

#### 18B — SHAP

**What it adds over importance.** Feature importance says what the model
uses overall. SHAP decomposes a SINGLE prediction into per-feature
contributions that SUM to that prediction, so an analyst sees "flagged
because velocity was 3× normal AND the amount was ₹36" rather than a
bare score. This feeds the Task 26 investigation view.

**Additivity verified, not assumed.** SHAP values + base value must
equal the raw prediction. **Max difference 1.07e-14** across 100 rows —
machine precision. If this failed the explanations would be wrong and
must not be shown to an analyst.

**A FEATURE REMOVED BECAUSE OF SHAP.** `card_age_days` came out at SHAP
rank 1 with **13.54%** of mean |SHAP|. Checking the distributions:

| | normal | fraud |
|---|---|---|
| mean | 44.10 | 46.57 |
| median | 44.08 | 48.35 |
| std | 26.01 | 24.67 |
| range | 0–89.98 | 0–89.64 |

Nearly identical — **no fraud signal at all**. And the 0–90 range is the
giveaway: the simulation is 90 days long, so this is **days since
simulation start, a TIME INDEX**, not card age. The model was splitting
on *when in the window* a transaction happened, fitting noise in how
2,034 training frauds happened to be distributed across 90 days.

**Removing it changed PR-AUC from 0.9674 to 0.9675** — the single
largest SHAP contributor was worth nothing. The overfit gap also
improved, 0.0307 → 0.0276. **This is the clearest demonstration in the
project that mean |SHAP| measures INFLUENCE, not USEFULNESS.**

**SHAP and gain disagree sharply, and both are right:**

| feature | SHAP rank | gain rank | moved |
|---|---|---|---|
| is_manual_entry | 39 | 2 | −37 |
| distinct_merchants_1h | 38 | 1 | −37 |
| is_new_mcc | 7 | 35 | +28 |
| merchant_txn_count | 9 | 31 | +22 |

`is_manual_entry` has SHAP **+12.55** on one CNP transaction — enormous.
But it is 1.0 on only ~290 of 115,566 rows, so its MEAN |SHAP| is tiny.
**Gain measures total objective improvement; SHAP measures average
per-row influence.** A feature decisive for 0.25% of rows and irrelevant
for the rest scores high on one and low on the other. Quote whichever
answers the question being asked.

**Top features by mean |SHAP| (v6):** `distance_from_home_km` 14.08%,
`amount` 8.73%, `merchant_is_online` 8.15%, `merchant_amount_std` 6.18%,
`device_card_count_7d` 4.77%.

**COLLUSION SHORTCUT — LOW-MODERATE, keep watching.** Task 10 warned the
model might learn "low-volume merchant" instead of "inflated amounts".
SHAP on v6: `merchant_txn_count` rank 9 (3.49%), `merchant_is_online`
rank 3 (8.15%), `merchant_card_count_7d` rank 15 (2.13%). **Not a
shortcut, but higher than v5** (rank 21, 1.70%), and the worked example
shows `merchant_txn_count = 131` with SHAP **−0.0129** — pushing AWAY
from fraud, the opposite of the feared behaviour. The six fixed
low-volume offline collusion merchants remain a synthetic-data
limitation worth stating in the report.

**A worked example — what an analyst would see (card_testing, score
0.99985, base rate 0.00004):**

| feature | value | SHAP |
|---|---|---|
| distinct_merchants_1h | 3.00 | **+3.77** |
| amount | 35.96 | **+3.03** |
| txn_count_5m | 3.00 | **+2.71** |
| distance_from_prev_km | 0.00 | **+2.65** |
| merchant_is_online | 0.00 | +1.11 |

Three merchants in an hour, a ₹36 amount, three transactions in five
minutes, zero distance moved. That is a card-testing burst described in
features, not a score.

---

#### 18C — MLflow

**Why it earns its place beyond tidiness.** Eight model versions exist
across Tasks 13–18 with results in separate JSON files. That works while
the project is fresh. It stops working at **Task 30**, when retraining
from analyst labels has to answer *"is this better than what is
deployed?"* — a question you cannot settle by comparing a number on
screen against a file from three weeks ago.

**Local file backend** (`./mlruns`). No server, no database, no cost.
Gitignored — regenerable from the report JSONs, and model artifacts
would bloat the repo.

**Backfilled from the report files**, so the history is reconstructed
from measurements rather than retyped: Task 12 baselines, Task 14
imbalance comparison and tuned model, Task 15 test evaluation, Task 16
threshold, Task 17 anomaly detectors and holdout experiment, Task 18
graph models.

**params vs metrics:** params are what was CHOSEN (hyperparameters,
feature count, strategy), metrics are what was MEASURED. Mixing them
makes the history unreadable — you search over params to improve
metrics.

**UI:** `mlflow ui --backend-store-uri mlruns` → http://127.0.0.1:5000

---

#### FINAL PHASE D MODEL: `models/lgbm_v6.txt`

58 features (48 base + 10 graph). **Validation PR-AUC 0.9675**,
precision@1300 0.3808, recall@1300 0.9763, overfit gap 0.0276, 152
trees. Per-pattern: card_not_present 100%, geo_impossible 100%,
card_testing 99.2%, merchant_collusion 100%, account_takeover 93.5%.

**NOTE:** v6 has NOT been evaluated on the test set. The Task 15 test
number (0.9573) belongs to v4. Evaluating v6 on test would be a third
access and should wait until Phase E is settled, if it happens at all.

**Interview talking points**

*"SHAP found a feature I would never have caught by eye. `card_age_days`
was my top contributor at 13.5% of mean |SHAP|, so I checked its
distribution: mean 44.1 for normal, 46.6 for fraud, identical spread.
No signal. And the range was 0 to 90 on a 90-day simulation — it was a
time index, not card age. The model was splitting on when in the window
a transaction happened. I removed it and PR-AUC went from 0.9674 to
0.9675. The single largest SHAP contributor was worth nothing, which is
the difference between influence and usefulness."*

*"My graph features worked, but not the one I expected. Distinct cards
on a device within an hour had a 6.4× fraud-to-normal ratio — by far the
strongest signal on paper — and the model used it for 0.00% of gain.
It was redundant with velocity features already in the model. What
actually helped were device and merchant volume counts, which are LOWER
for fraud, and they lifted merchant-collusion recall from 96.6% to 100%
because collusion is a merchant-level property my per-transaction
features could not see."*
## PHASE E — SERVING

### Task 19 — FastAPI scoring service ✅ 20 Oct

**Files:** `src/streamguard/api/{__init__,schemas,scorer,main}.py`

#### ARCHITECTURE DECISION — Option A: in-memory state, warmed at startup

The feature engine is **stateful**. `compute_features()` reads this
card's running mean, its last location, its 5-minute velocity. That
state has to come from somewhere. Three options were weighed:

| option | pro | con |
|---|---|---|
| **A: in-memory, warmed at startup** | fast, no round-trip in the hot path | lost on restart, single process |
| B: state in PostgreSQL | durable, scales horizontally | a DB query inside the latency budget |
| C: client sends features | trivial, fastest | moves training/serving skew to the client |

**Chose A**, because Task 20 measures the latency budget and option B
puts a database query in the critical path before anything has been
measured. A also makes the Task 20 comparison meaningful: measure A,
then measure B, and show the cost of durability in milliseconds.
C was ruled out — it moves the hard problem to the client, and
training/serving skew is the failure this project exists to address.

**Costs of this choice, stated plainly:** state is lost on restart;
warm-up replays the event log (8.5s for 50k events, so roughly 2
minutes for the full 791k); one process only.

#### THE SECURITY RULE

The request schema sets `extra="forbid"`, which **rejects `is_fraud`
and `fraud_type`**. The Task 8 event payload carries both (a
deliberate, documented choice), so a client could send them. A client
sending the answer is either confused or probing.

Verified: posting `is_fraud: false` returns **422** with
`type: extra_forbidden`, `loc: ["body", "is_fraud"]`. Pydantic rejects
it before any project code runs.

#### BUG FOUND IN TESTING — missing idempotency

The first manual test returned `decision: block` on an ordinary ₹845
restaurant purchase, with `txn_count_5m = 3`,
`distance_from_prev_km = 0` and `implied_speed_kmh = 99999`.

**Cause:** the same transaction was POSTed three times while testing
the form. Each POST called `score()` → `computer.process()`, which
**updates state**. By the third call the card looked like it was being
tested: three transactions, same place, seconds apart. The 99,999 is
the implied-speed sentinel — zero distance over ~zero seconds, the same
division the Task 13.7C generator bug produced.

**Fix:** a bounded `transaction_ref` cache (100,000 entries, LRU by
insertion). A ref already scored returns the cached result **without
touching state**. Task 8 established that consumers must be idempotent
under at-least-once delivery; the same applies to a retried HTTP POST.

**Verified:** two identical POSTs → `scored: 1`,
`duplicates_rejected: 1`. The `scored` count staying at 1 is the proof
that state was touched once.

#### VERIFIED BEHAVIOUR

| test | result |
|---|---|
| `/health` | ready, lgbm_v6, 58 features, 6,967 cards, 792 merchants |
| ordinary ₹845 purchase at home | **approve**, p = 0.000155, **3.4 ms** |
| ₹94,500 jewellery, Dubai, 3am, manual entry | **block**, p = 0.756, **46.7 ms** |
| `is_fraud` in the body | **422 extra_forbidden** |
| duplicate POST | `duplicate: true`, state untouched |

**The high-risk explanation, as an analyst would see it:**

| feature | value | SHAP |
|---|---|---|
| is_manual_entry | 1 | **+6.40** |
| distance_from_home_km | 2,066.22 | +1.20 |
| hour_of_day | 3 | +0.72 |
| is_new_device | 1 | +0.65 |
| amount | 94,500 | +0.56 |

Jaipur → Dubai computed as 2,066 km from the submitted coordinates,
which matches reality. This is the Task 26 investigation view already
working end to end.

#### LATENCY — A PREVIEW OF TASK 20

**3.4 ms approved vs 46.7 ms blocked.** SHAP costs roughly 40 ms, and
it only runs on the non-approve path:

> *"Only explain what a human will look at. Explaining every approved
> transaction would double the cost of the common path for an
> explanation nobody reads."*

**That 46.7 ms is already most of a 100 ms budget**, on a warm cache
with a single request and no concurrency. Task 20 measures p50/p95
properly, but the shape of the problem is already visible: SHAP is the
cost, and the decision to skip it on approvals is what keeps the common
path cheap.

#### SIGNATURES DISCOVERED (do not guess these again)

- `FeatureComputer.process(payload: dict) -> dict[str, float]` — takes
  the raw event payload dict, returns 49 floats
- `FileEventConsumer(root: Path, topic="transactions", group="default",
  from_beginning=False)` — root is `data/events`, NOT
  `data/events/transactions`
- `StateStore` has `card()`, `customer()`, `merchant()`, `clear()`,
  `summary()` — **no `.cards` attribute**

**Interview talking point**

*"My first manual test of the API returned 'block' on an ordinary ₹845
restaurant purchase. The reasons showed three transactions in five
minutes and an implied speed of 99,999 km/h — but I had only sent one
transaction, three times, while testing the form. Each POST was folding
the same transaction into the feature state, so the card looked like it
was being card-tested. The fix was idempotency: a transaction_ref
already scored returns the cached result without touching state. It is
the same rule my event log already had for at-least-once delivery, and
I had not carried it into the HTTP layer."

### Task 20 — Latency measurement ✅ 20 Oct

**Files:** `src/streamguard/api/bench.py`, `scripts/measure_latency.py`,
`scripts/measure_http_latency.py`

**Budget: 100 ms** — the window between a swipe and the authorisation
decision. The project record called for "a measured latency budget, not
a guessed one"; this is the measurement.

**Percentiles, not the mean.** A service with a 3 ms mean and a 400 ms
p99 fails one request in a hundred, and that is the one the customer
notices at the checkout.

#### 20.3 — In-process (no HTTP, no network, no concurrency)

**By stage, 2,000 transactions:**

| stage | p50 | p95 | p99 | max |
|---|---|---|---|---|
| features | 0.15 | 0.25 | 0.34 | 1.08 |
| graph | 0.28 | 0.48 | 0.98 | 1.63 |
| predict | 0.23 | 0.40 | 0.60 | 5.25 |
| **shap** | **6.78** | 8.66 | 10.96 | 10.96 |
| **total** | **0.69** | **1.26** | **7.13** | **11.26** |

**By decision path:**

| path | n | p50 | p95 | p99 |
|---|---|---|---|---|
| approve (no SHAP) | 1,975 | 0.69 | 1.13 | 1.72 |
| review/block (SHAP) | 25 | 7.50 | 9.23 | 11.26 |

**SHAP costs 6.8 ms — 10.9× the approve path — but runs on only 1.2%
of traffic.** That is the Task 19 design decision paying off: explain
only what a human will look at. Explaining every approved transaction
would make the common path 10× more expensive for an explanation
nobody reads.

**Verdict: PASS at p99 with 14× headroom** (7.13 ms against 100 ms).
Throughput 1,227/sec single-process.

#### 20.4 — Over HTTP

| | concurrency 1 | concurrency 4 |
|---|---|---|
| client p50 | 15.84 ms | 27.21 ms |
| client p95 | 32.38 ms | 43.09 ms |
| client p99 | **34.14 ms** | **49.02 ms** |
| client max | 36.09 ms | 55.66 ms |
| server p50 | 1.38 ms | 2.27 ms |
| throughput | 55 req/sec | **144 req/sec** |
| decisions | approve 500 | approve 500 |

**Both PASS at p99.**

**The model is not the bottleneck — the framework is.** HTTP overhead is
14.46 ms at concurrency 1, **91% of the round trip**. That is FastAPI
routing, Pydantic validation, JSON serialisation and loopback
networking. Scoring itself is 1.38 ms.

**Concurrency gives sub-linear throughput:** 4× the clients gives 2.6×
the throughput (55 → 144/sec), and server p50 rises 1.38 → 2.27 ms.
**This is the cost of Option A.** `/score` is a synchronous function
doing CPU work, so Python's GIL serialises concurrent requests inside a
single uvicorn worker — and workers cannot be added without losing the
shared in-memory state that Option A depends on. A durable state store
(Option B) is what would allow horizontal scaling, at the cost of a
round-trip per request.

#### TWO MEASUREMENT BUGS FOUND AND FIXED

Both produced plausible-looking numbers that were wrong — the same
failure mode as every other bug in this project.

**1. The benchmark measured its own cache.** A second run reused the
same `BENCH%012d` transaction_refs, so the Task 19 idempotency cache
returned cached results. Reported server p50 **0.01 ms** and
**78,441/sec** — physically impossible, and the giveaway was identical
decision counts across two runs. Fixed by making refs unique per run.

**2. Warm-up and benchmark offsets drifted apart.** The server was
warmed with 50,000 events while the benchmark replayed from offset
200,000 — a 150,000-event gap. Every card arrived with a stale
last-seen time, producing huge `seconds_since_prev` values and
distorted velocity features. Result: `approve 53, review 231, block
216` — 89% flagged against a 0.37% fraud rate, and server p50 inflated
from 2.10 ms to 12.86 ms because nearly everything hit the SHAP path.
Fixed by warming to the same offset the benchmark starts from.

**The lesson is the one from Phase D again:** the decision counts, not
the latency numbers, were what exposed both bugs. A latency figure
alone looks fine whatever is wrong with the data behind it.

**Interview talking point**

*"My record called for a measured latency budget rather than a guessed
one, so I measured it at both layers. In-process scoring is 0.69 ms at
p50 and 7.13 ms at p99 against a 100 ms budget. Over HTTP it is 15.8 ms
and 34.1 ms — so 91% of the round trip is FastAPI, Pydantic and
loopback, not the model. SHAP is the expensive part at 6.8 ms, but it
only runs on the 1.2% of traffic a human will actually review."*

*"The measurement itself had two bugs, and both produced believable
numbers. One run reported 78,000 requests a second because the
benchmark was re-sending the same transaction IDs and hitting my own
idempotency cache. Another showed 89% of transactions being blocked
because the server's feature state was warmed to a different point in
the event log than the benchmark replayed from. Both times the decision
counts gave it away, not the latency."*

### Task 21 — Decision engine + business rules ✅ 20 Oct

**Files:** `src/streamguard/api/decisions.py`,
`scripts/test_decisions.py`, edits to `scorer.py` and `schemas.py`

**Why this is not just a threshold.** A score answers *"how likely is
this fraud?"*. A decision answers *"what do we do?"*, and that question
has inputs the model does not have:

- a card **reported stolen** must be blocked at any score — the model
  has never seen the theft report, only behaviour
- a **regulatory value limit** requires review regardless of risk
- a **merchant under investigation** needs every transaction held
- **analyst capacity is finite**, so the review queue has a budget

Putting these in the model would be wrong: they are policy, they change
weekly, and they must be auditable one rule at a time. Putting them in
the scorer would mix a measurement with a business decision.

**Precedence.** All rules are evaluated, not just the first match, so
the audit trail records everything that applied. **The most severe
outcome wins.** A rule can only make a decision MORE severe — except
`card_trusted`, which is explicitly bounded by an amount and cannot
override a block.

**Every decision records why.** The response carries `decision_source`
("rule" or "model"), `model_decision` (what the score alone said),
`overridden`, the full `rules_fired` list, and a plain-English
`decision_explanation`. An analyst asked *"why was this blocked?"* gets
an answer that names the rule or the score.

#### The rules

| rule | outcome | why the model cannot do it |
|---|---|---|
| `card_blocked` | BLOCK | theft report is outside the transaction stream |
| `merchant_blocked` | BLOCK | operations decision |
| `device_blocked` | BLOCK | operations decision |
| `very_high_value` ≥ ₹1,000,000 | BLOCK | one wrong block costs less than one fraudulent approval at this size |
| `high_value` ≥ ₹200,000 | REVIEW | reporting obligation; a low score does not remove it |
| `merchant_watched` | REVIEW | investigation status |
| `card_trusted` < ₹100,000 | APPROVE | the only severity-reducing rule, and bounded |

Thresholds come from Task 16, not from 0.5: block ≥ 0.03061, review ≥
0.01113, derived from the 25:1 cost asymmetry.

#### Verified — 10/10 cases pass

| case | expected | source |
|---|---|---|
| low score, nothing special | approve | model |
| score above review threshold | review | model |
| score above block threshold | block | model |
| **stolen card, p = 0.0001** | **block** | **rule** |
| watched merchant, low score | review | rule |
| high value, low score | review | rule |
| very high value, low score | block | rule |
| trusted card, mid score | approve | rule |
| **trusted card CANNOT bypass a block score** | **block** | **model** |
| **trusted card CANNOT bypass a high value** | **review** | **rule** |

The last two matter most: **trust is not a licence to skip a strong
fraud signal or a regulatory limit.** A bypass rule without bounds is
how a whitelist becomes an attack surface.

**Example explanations an analyst reads:**

> BLOCK by rule 'card_blocked' (card is on the blocked list (reported
> stolen or compromised)), overriding the model's approve at p=0.0001

> REVIEW by rule 'high_value' (amount 250,000 requires review above
> 200,000), overriding the model's approve at p=0.0010

#### Verified live over HTTP

| request | decision | source | rules fired |
|---|---|---|---|
| ₹94,500 Dubai, 3am, manual entry | block | model | none |
| ₹250,000 same transaction | block | model | `high_value` (wanted review) |

The second shows precedence working: the rule asked for review, the
model said block at p=0.9724, and block won. The explanation names
both — *"rule 'high_value' ... and the model agree"*.

**Interview talking point**

*"The model produces a score; the decision engine produces a decision,
and they are deliberately separate. A card reported stolen this morning
must be blocked even though the model scores it at 0.0001 — the model
has never seen the theft report, only behaviour. I evaluate every rule
rather than stopping at the first match, because the audit trail should
record everything that applied, and the most severe outcome wins. The
one rule that can reduce severity, a trusted card, is bounded by amount
and cannot override a block score or a regulatory limit — I have
explicit test cases for both, because an unbounded whitelist is an
attack surface."*

### Task 22 — Case management API ✅ 20 Oct

**Files:** `src/streamguard/api/cases.py`, `scripts/test_cases.py`,
endpoints added to `main.py`

**Until now a score vanished after the HTTP response.** Three things
need it to persist:

1. an analyst must work a queue of flagged transactions
2. their verdict is the **only ground truth this system gets after
   deployment** — Task 30 retrains on exactly these labels
3. an audit trail must answer *"who decided what, when, and why"*,
   which is a regulatory requirement

The Task 4B schema was built for this and needed no migration:
`decisions` (features as JSONB), `cases` (the queue), `case_events`
(append-only audit log).

#### Priority is score × amount, not score

A 0.95 score on a ₹50 card-testing probe costs ₹50. A 0.40 score on
₹200,000 costs four thousand times more. Analyst time should go where
the exposure is — the same reasoning as the Task 16 cost threshold.

**Verified in the queue:**

| case | priority | score | amount |
|---|---|---|---|
| CASE0000000024 | **2** | 0.9796 | ₹15,424 |
| CASE0000000016 | 3 | **0.9930** | ₹2,451 |

The lower-scoring case ranks higher. That is the sort working.

#### The verdict is the label

`confirmed_fraud` and `legitimate` are usable as training labels.
**`inconclusive` is recorded but explicitly NOT usable** — an analyst
who could not decide has not said the transaction was fine, and
training on it as a negative would teach the model that genuine fraud
is normal. The response carries `usable_as_label` so the caller cannot
misread it.

Guards, both verified returning 400:
- submitting a second verdict → *"case already closed with verdict
  'confirmed_fraud'"*
- an invalid verdict → the valid set is named in the error

#### Features stored: 61, not 58

The `decisions.features` JSONB stores **49 base + 12 graph = 61**,
while the model uses 58. The three extra are `ring_size` and
`ring_fraud_density` (dropped at Task 18A as dead) plus the base
feature dropped at 18B. Storing a few unused features costs nothing
and makes the record more complete for skew detection.

**Why this matters at all:** the Task 4B design note said features are
stored as JSONB so training/serving skew can be **detected** later, and
you can only detect it if you recorded it. An earlier version stored
only the 49 base features, which would have left the graph features
unverifiable. Fixed by calling `graph.compute()` — read-only, so it
does not double-update the state that `score()` already advanced.

#### Endpoints

| endpoint | purpose |
|---|---|
| `GET /cases` | the queue, most urgent first |
| `GET /cases/{ref}` | one case with SHAP reasons and full audit trail |
| `POST /cases/{ref}/assign` | claim a case |
| `POST /cases/{ref}/verdict` | close it with a conclusion |
| `GET /cases-stats` | decision counts, case states, labels available |

**Persisting is best-effort.** A database problem must not stop an
authorisation decision being returned, so the write is wrapped and
failures are logged, not raised.

#### Verified end to end

12 known-fraud transactions scored → 10 flagged → case opened →
assigned → investigated → verdict submitted → closed.

**Audit trail for CASE0000000024:**
19:16:45 case_opened by system
{score: 0.9796, action: block, decision_source: model}
19:16:45 assigned by analyst_lasya
19:16:45 verdict_submitted by analyst_lasya
{verdict: confirmed_fraud, usable_as_label: true}

**The investigation view** shows what the analyst reads:
`is_manual_entry = 1.00` with SHAP **+12.10**, then amount, implied
speed and merchant counts. That is the Task 26 UI's data already
available over HTTP.

**A testing quirk, not a production path:** re-running `test_cases.py`
creates duplicate cases for the same transactions, because the
idempotency cache is per-process and clears on restart while the
database does not. A real stream never replays a `transaction_ref`.

**Interview talking point**

*"The analyst's verdict is the only ground truth the system gets after
deployment, so the case API treats it as a training label rather than a
status field. I made 'inconclusive' explicitly unusable — an analyst
who could not decide has not told me the transaction was legitimate,
and training on it as a negative would teach the model that genuine
fraud is normal. The queue also sorts by score times amount rather than
score, because a 0.95 on a ₹50 card-testing probe is worth less analyst
time than a 0.40 on ₹200,000."*


A caller cannot act as someone else, which is what makes the Task 22
audit trail meaningful and the Task 30 training labels attributable.

#### Security details worth defending

**Timing-safe login.** An unknown username still runs a bcrypt hash
before returning, so a missing user and a wrong password take the same
time. Otherwise the response time tells an attacker which usernames
exist. Both paths return the identical message, `invalid credentials`.

**The dev secret cannot reach production.** `verify_configuration()`
raises at startup if `STREAMGUARD_JWT_SECRET` is still the development
default while `STREAMGUARD_ENV` says production, and logs a warning
otherwise. A dev convenience that silently survives into production is
how a service ends up with forgeable tokens.

**Short-lived tokens with a `jti`.** 60 minutes by default, each with a
unique id, so a single token can be revoked later without invalidating
every token the user holds. A stolen token is useful for minutes, not
forever.

**JWT rather than sessions**, because Task 19 chose stateless scoring —
a token the server does not have to look up is one fewer thing in the
hot path measured at Task 20.

**`/health` stays open.** A load balancer needs it.

#### Dependency note — a real version conflict

`passlib 1.7.4` + `bcrypt 5.0.0` fails with *"module 'bcrypt' has no
attribute `__about__`"*: passlib predates bcrypt 4 and reads an
attribute that no longer exists. **Pinned `bcrypt==3.2.2`** in
`requirements.txt`. Also added `python-jose[cryptography]==3.3.0` and
`passlib[bcrypt]==1.7.4`.

Passwords are capped at 72 bytes in `UserStore.add()`, because bcrypt
raises above that — enforced at the boundary rather than discovered in
production.

**Interview talking point**

*"My case API had an audit trail, but the actor field came from the
request body — the caller told the server who they were. That is not an
audit trail. I added JWT auth with three roles and removed the analyst
field from the request entirely; the username now comes from the
verified token. The role that mattered most was the service account for
the payment switch, which calls the scoring endpoint thousands of times
a day and is therefore the most exposed credential. It can score and
nothing else — a compromised switch key cannot read the analyst queue
or close cases."*


Fixed by writing the files with a short Python script
(`write_app.py`, `write_css.py`). **The lesson is the Phase D one
again: check the artefact, not the tool that claims to have produced
it.**

**Interview talking point**

*"I proxied the API through Vite rather than enabling CORS, because
the alternative is shipping a permissive CORS policy to production to
solve a development-only problem. The frontend also mirrors the
server's permission map to hide controls a role cannot use — but that
is cosmetic, not security. The server returns 403 and anyone can edit
JavaScript in their own browser; the mirror just avoids showing a
button that would fail."*
### Task 25 — Live transaction stream ✅ 20 Oct

**Files:** `scripts/replay_stream.py`, `frontend/src/LiveStream.jsx`,
`/recent-decisions` endpoint, tab shell in `App.jsx`

#### The feeder had to exist first

The event log held 791,109 transactions but **nothing replayed them
into the API**. A "live stream" page with no stream behind it would be
a mock, and the project record forbids replacing a hard feature with a
placeholder. `replay_stream.py` feeds the scoring API at a chosen rate
through the same HTTP path a payment switch would use.

**It authenticates as `payment-switch` (role `service`)** — the Task 23
role that can score and nothing else. The demo therefore exercises the
real authorisation path, not a bypass.

#### Polling, not websockets

The page refreshes every 2 seconds. **A dropped poll is self-healing;
a dropped socket needs reconnection logic.** For a console watched by a
handful of analysts, that complexity is not worth buying.

`since_id` means the client asks only for rows it has not seen.
Re-sending the whole window every poll would grow the payload with the
table and make the page slower the longer it runs.

#### Verified live

543 scored at 5/sec, **mean latency 2.1 ms**, rows streaming with real
city names, amounts and probabilities. Stat tiles for scored /
approved / review / blocked / flagged % / mean latency.

**A number that needs reading carefully.** The page showed **3.87%
flagged** against a 0.37% fraud rate — about 10× too high. The totals
are cumulative over the whole `decisions` table, which still contains
24 deliberately-known-fraud rows from the Task 22 `test_cases.py`
runs. **Not a bug in the page: it is telling the truth about the
table.** The figure falls toward the real rate as ordinary traffic
dilutes the seeded cases. Worth stating because a flagged-rate tile is
exactly the kind of number someone reads as live and acts on.

#### A Vite/editor trap, again

`App.jsx` was written **truncated** — the file ended at `</main>` with
the closing `</div>`, `)` and `}` missing, producing
`[PARSE_ERROR] Unexpected token`. Same class of failure as Task 24:
the editor reported success, the file on disk was wrong. Diagnosed by
counting tags from the terminal rather than reading the editor:
python -c “import pathlib; t=pathlib.Path(‘src/App.jsx’).read_text().splitlines(); print(len(t)); print(sum(1 for l in t if ‘</main>’ in l))”

**Interview talking point**

*"The live stream page needed something to be live, so I wrote a
replay feeder that pushes the event log through the real HTTP scoring
endpoint, authenticating as the service role a payment switch would
use. The page polls rather than using websockets — a dropped poll is
self-healing, a dropped socket needs reconnection code — and it asks
only for decisions newer than the highest id it holds, so the payload
does not grow with the table."*

### Task 26 — Case queue + investigation view ✅ 20 Oct

**Files:** `frontend/src/CaseQueue.jsx`, styles in `App.css`

Frontend only — the Task 22 API already had everything needed.

#### List-then-detail, not separate pages

Two panes: queue left, selected case right. **An analyst works through
a queue and should not lose their place on every verdict.** After a
verdict closes a case the pane moves to the next one automatically.

#### The SHAP bars are the point

The investigation view renders the stored explanation as proportional
bars, so the dominant feature is visible before any number is read.

**A card-testing case (score 0.9985, ₹81.11):**

| feature | value | SHAP |
|---|---|---|
| distinct_merchants_1h | 3 | +3.786 |
| distance_from_prev_km | 0 | +2.955 |
| amount | 81.11 | +2.823 |
| txn_count_5m | 2 | +2.229 |
| merchant_is_online | 0 | +1.099 |

Three merchants in an hour, zero distance moved, a trivial amount, two
transactions in five minutes. **A probe burst described in features an
analyst can act on**, not a score.

**A card-not-present case (score 0.9796, ₹15,423.56):**
`is_manual_entry = 1` at **+12.101**, every other feature under +0.5 —
the Task 18B finding made visual. One feature decides the case.

#### The verdict UI states what the verdict IS

Three buttons with the consequence written next to them:
`confirmed_fraud` and `legitimate` are training labels;
**`inconclusive` is recorded but never used**, with the reason in the
UI — *an analyst who could not decide has not said the transaction was
legitimate.* A dropdown labelled "status" would hide that.

#### Verified end to end

Nine verdicts submitted through the UI, each attributed to the
**verified token identity**, not a form field:
19:16:45 case_opened by system
19:16:45 assigned by analyst_lasya
19:16:45 verdict_submitted by analyst_lasya

Closed view shows the verdict, who closed it, and the notes.

#### Bug found and fixed — a stale detail pane

After submitting a verdict the case closed in the database but the
pane still showed the buttons. **The server was correct; the UI was
not refreshing.** `load()` reloaded the queue, the closed case dropped
out of the "Open" list, and `selected` pointed at a case no longer
present — so the detail never re-rendered.

**Diagnosed by querying the database rather than trusting the screen:**
the verdicts were all there with the right actors and notes. Fixed by
re-selecting the first remaining case when the chosen one leaves the
list.

**The same lesson as Tasks 24 and 25:** check the artefact, not the
surface that claims to have produced it.

**Interview talking point**

*"The investigation view renders the stored SHAP values as
proportional bars, so an analyst sees which feature decided the case
before reading a number. On a card-testing probe it shows three
merchants in an hour and zero distance moved; on a card-not-present
case one feature carries +12 and everything else is under +0.5. I also
labelled the verdict buttons with what they mean for training —
'inconclusive' is recorded but never used as a label, because an
analyst who could not decide has not said the transaction was
legitimate."*
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
## WHERE I AM RIGHT NOW → **25 of 32 tasks complete.**

### What exists and works right now

| | |
|---|---|
| Database | PostgreSQL 17.11, 9 tables, Alembic migrations applied |
| Data | 791,109 transactions over 90 days, 3,000 fraud (0.379%) across 5 patterns |
| Model | LightGBM v6, 58 features (48 base + 10 graph). Val PR-AUC 0.9675, gap 0.0276. v4 (49 feat) scored test 0.9573 |
| Decision | Threshold 0.03061 (cost-optimised, 25:1). Test: recall 0.9499, ₹344,400 saved vs 0.5 |
| Anomaly | Isolation Forest + Mahalanobis, fitted on normal only. Catch 93.7% / 100% of patterns LightGBM scores 0.0% on |
| Tests | 44 passing — leakage, integrity, split, generator |
| Explainability | SHAP, additivity verified to 1e-14. Per-transaction explanations ready for the Task 26 analyst view |
| Tracking | MLflow local file backend, ~25 runs backfilled from Tasks 12–18 |
| API | FastAPI `/score` + `/health`. In-process p50 0.69 ms / p99 7.13 ms. Over HTTP p50 15.8 ms / p99 34.1 ms. Budget 100 ms — PASS |
| Decisions | Policy rules + cost thresholds, most-severe-wins, full audit trail. 10/10 rule cases pass |
| Cases | Analyst queue sorted by exposure, verdicts as training labels, append-only audit trail. 61 features stored per decision |
| Auth | JWT, 3 roles (service/analyst/risk_manager), permissions as data. 7/7 access cases pass. Audit identity from token |
| Frontend | React + Vite, 3 tabs. Live stream polling /recent-decisions every 2s, fed by replay_stream.py at a chosen rate |
| Frontend | React + Vite, 3 tabs. Live stream (polling), case queue with SHAP investigation view and verdict flow |
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

- **18:** graph features (NetworkX), SHAP explanations, MLflow tracking
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
- ~~Account takeover weak~~ **CLOSED at Task 13** — 83.9% recall with
  trees vs 52.3% linear. Test: 94.2%.
- ~~Collusion shortcut (`merchant_txn_count`)~~ **LOW RISK** — rank 28,
  0.21% of gain at Task 14. Confirm with SHAP at Task 18.
- ~~Overfitting gap 0.0799~~ **CLOSED at Task 14** — 0.0297 after
  removing `is_unbalance` and tuning.
- ~~Probabilities calibrated?~~ **CONFIRMED at Task 15** — ECE 0.00053
  on test. Task 16 uses them directly.
- **Test set accessed twice**, both logged with reasons (Task 15
  evaluation, Task 16 threshold reporting). No tuning against it.
- **Run both models in production** (Phase E decision): LightGBM scores
  0.0% on unseen patterns; the detectors cover that gap. Needs a
  combination rule — max score, or route anomaly-only hits to review.
- **merchant_collusion distance** mean 258 km vs median 20.5 km — the
  25-try rejection loop occasionally fails for isolated merchants.
  Median is fine; not worth a regeneration.
- **psycopg ResourceWarning** — still open, fix before Phase E.
- **README must state** that 0.9573 describes the generator, not the
  real world, and that three label proxies were found and fixed at
  Task 13.7.
- **No latency measurement yet** — Task 20. The record calls a measured
  latency budget a defining feature of this project.
- **v6 not evaluated on test.** The 0.9573 test number is v4's. A third
  test access should wait until Phase E is settled, if at all.
- **Collusion shortcut LOW-MODERATE** — `merchant_txn_count` SHAP rank 9
  (3.49%) in v6, up from rank 21 in v5. Not a shortcut, but watch it.
- **`ring_size` failed** — the generator assigns devices randomly, so
  there are no fraud rings to detect. State as a synthetic-data limit.
- ~~SHAP cost unknown~~ **MEASURED at Task 20** — 6.8 ms, on 1.2% of
  traffic. Not a problem.
- **Concurrency is sub-linear** — 4× clients gives 2.6× throughput, GIL
  bound in a single worker. Inherent to Option A; horizontal scaling
  needs a durable state store.
- **Warm-up/benchmark offsets must match** or the decision mix is
  nonsense. Set `STREAMGUARD_WARM_EVENTS` to the benchmark's `--skip`.
  - **Users are in-memory** — seeded at startup with dev passwords. A
  real deployment uses the bank's identity provider; the point of
  Task 23 was the authorisation model, not user storage.
- **Dev JWT secret** — set `STREAMGUARD_JWT_SECRET` and
  `STREAMGUARD_ENV=production` before any real deployment. The service
  refuses to start with the default in production.

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