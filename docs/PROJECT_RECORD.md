# STREAMGUARD — PROJECT HANDOFF RECORD

**Last updated:** 18 Oct 2026
**Status:** Phase A complete, Phase B complete (Tasks 1–6). Starting Task 7.

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

**OPEN DECISION (due at Task 8):** whether the event log is a lightweight
file-backed log I write myself, or real Apache Kafka via WSL2. 8 GB RAM makes
Kafka risky. **Not decided yet — my call to make.**

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
7. ⬜ **← CURRENT.** Fraud pattern injection + labelled dataset export

**PHASE C — STREAMING**
8. ⬜ Event log design + producer
9. ⬜ Consumer with offsets + replay
10. ⬜ Online feature engine (rolling windows, velocity, z-scores)
11. ⬜ Offline feature store + point-in-time correctness + leakage tests

**PHASE D — MACHINE LEARNING**
12. ⬜ Train/test split by **time** (never random) + baseline model
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
0e1cc41  Task 6: transaction generator with realistic temporal patterns (IST fix)
e191598  Task 5: population generator and PostgreSQL loader
846daa6  Task 5.1: reference data and geographic helpers
2ab5b20  Task 4B: database schema with eight tables and Alembic migrations
511a694  Task 4A: PostgreSQL connection, session management, health check
bf30d15  Task 3: configuration management and structured logging
e164c0e  Task 2: add pinned dependencies for app and development
f4f9821  Task 1: project skeleton, virtual environment, gitignore

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

**Starting Task 7 — fraud pattern injection.**

Five patterns to inject, each with a different signature so the model must learn
different signals rather than memorising one rule:

| Pattern | Signature | Should be caught by |
|---|---|---|
| Card testing | Burst of tiny transactions in minutes | Velocity features |
| Account takeover | Behaviour changes abruptly — new device, new categories | Deviation from customer baseline |
| Geo-impossible | Same card, two cities, impossible speed | `implied_speed_kmh` |
| Merchant collusion | Complicit merchant inflating amounts | Merchant-level aggregates |
| Card-not-present | Online, high-value category, no card present | Channel + category + amount |

Target fraud rate: **0.004** (~3,100 of 788,000 rows). This brutal imbalance is
the real challenge — it's why accuracy is a useless metric here and why Task 16's
cost-based thresholds matter.