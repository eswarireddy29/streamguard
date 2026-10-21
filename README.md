\# StreamGuard



\[!\[tests](https://github.com/eswarireddy29/streamguard/actions/workflows/tests.yml/badge.svg)](https://github.com/eswarireddy29/streamguard/actions/workflows/tests.yml)



Real-time transaction fraud detection and investigation platform. Scores a

card transaction in the window between the swipe and the authorisation

decision, explains why it was flagged, routes it to an analyst, and feeds

their verdict back into retraining.



Python - FastAPI - PostgreSQL - LightGBM - React - zero paid services.



\---



\## Read this before the numbers



\*\*The data is synthetic and separable by design.\*\* A generator produces

791,109 transactions over 90 days with five hand-written fraud patterns.

A model that catches them has learned those patterns, not real-world

fraud. The headline PR-AUC of 0.9573 describes this generator.



How separable: on the held-out test set, 110,805 of 123,117 rows sit in

the lowest score bucket and contain \*\*one\*\* fraud between them. Real card

fraud does not separate like that.



Three label proxies were found and fixed during development. There may be

more the audit did not detect.



\---



\## Results



| | |

|---|---|

| Data | 791,109 transactions, 90 days, 3,000 fraud (0.379%) |

| Model | LightGBM, 58 features (48 behavioural + 10 graph) |

| Test PR-AUC | \*\*0.9573\*\* - 256.8x a random model |

| Calibration | ECE 0.00053 (probabilities usable as probabilities) |

| Threshold | 0.03061, from a 25:1 cost asymmetry - not 0.5 |

| Test recall at that threshold | 0.9499 (vs 0.7778 at 0.5) |

| Latency | p50 0.69 ms in-process, 15.8 ms over HTTP; budget 100 ms |

| Capacity | 62 req/sec at 4 concurrent clients, GIL-bound |

| Tests | 158 passing |



Accuracy is not reported. At 0.379% fraud, predicting "never fraud" scores

99.62% and catches nothing.



\---



\## Architecture



generator --> PostgreSQL --> file-backed event log --> feature engine (58)

|

LightGBM --> SHAP --> decision engine (rules + cost)

|

approve / review / block --> analyst queue

|

verdict --> training labels --> retrain





\*\*No Kafka.\*\* Its JVM needs \~1.5-2 GB against an 8 GB budget shared with

PostgreSQL, VS Code and a React dev server. The event log is a

file-backed append-only log behind the same producer/consumer abstract

base classes, so a Kafka implementation is a subclass, not a rewrite.



\*\*Feature state lives in memory\*\*, warmed at startup by replaying the

event log. The alternative - a database round-trip per request - was

rejected because it sits inside the latency budget. The cost is measured:

state is lost on restart, and one process cannot scale horizontally.



\*\*The governing rule:\*\* a feature computed at time T may use only events

strictly before T. Enforced structurally - `compute\_features()` reads

state, `update\_state()` writes it, and `process()` is the only place the

order is encoded. Violating it is silent: results look \*better\*, and the

model fails in production where the future is not available.



\---



\## Running it



Needs Python 3.11 and PostgreSQL 17.



```bash

python -m venv .venv

.venv\\Scripts\\activate

pip install -r requirements.txt

pip install -e .



copy .env.example .env

alembic upgrade head

```



Build the data (\~20 minutes, not committed - 617 MB event log,

270 MB parquet):



```bash

python scripts/generate\_transactions.py

python scripts/load\_event\_log.py

python scripts/build\_features.py

python scripts/build\_graph\_features.py

```



Run the service and console in separate terminals:



```bash

set STREAMGUARD\_WARM\_EVENTS=200000

uvicorn streamguard.api.main:app --port 8000



cd frontend \&\& npm install \&\& npm run dev

```



Console at `http://localhost:5173`, API docs at `http://localhost:8000/docs`.

Development users: `analyst`, `manager`, `payment-switch`.



Feed it live traffic:



```bash

python scripts/replay\_stream.py --rate 10

```



\---



\## Findings worth reading



\*\*A leak that would have shipped.\*\* The first LightGBM scored PR-AUC

0.9932 and feature importance showed `is\_new\_device` carrying 58.65% of

total gain - a feature earlier analysis had recorded as the \*weakest\*

signal in the project. Four of five fraud patterns passed `device\_ref=None`

to the generator, and the feature engine reads a missing device as "new

device". The generator was labelling its own fraud. After the fix the

score fell to 0.9201 - and the gap between trees and logistic regression

grew from 0.07 to 0.21, because both models had been reading the same

giveaway.



\*\*Class weighting was hurting.\*\* `is\_unbalance=True` is the conventional

choice at 0.37% prevalence. Measuring it: removing it gained 0.03 PR-AUC,

halved the overfitting gap, needed 12x fewer trees, and restored

probability calibration.



\*\*Rule systems reach 1.0x lift here.\*\* The pre-ML baseline - velocity,

impossible travel, amount ratio - performs no better than random once the

generator stops announcing its fraud.



\*\*Supervised models catch 0% of patterns they have not seen.\*\* Holding

out one fraud pattern at a time: LightGBM caught 0 of 254 card-testing

frauds and 0 of 52 card-not-present frauds. An unsupervised detector

fitted only on normal traffic caught 93.7% and 100% of the same rows.

They fail on different things, which is the argument for running both.



\*\*SHAP found a top feature that was worthless.\*\* `card\_age\_days` ranked

first at 13.54% of mean |SHAP|. Its distributions were nearly identical

(mean 44.1 normal vs 46.6 fraud), and its 0-90 range on a 90-day

simulation gave it away as a time index. Removing it changed PR-AUC from

0.9674 to 0.9675.



\*\*The model is 4 ms of a 50 ms request.\*\* Per-stage timing: features 1.25

ms, graph 0.95 ms, prediction 1.91 ms. The rest is framework,

serialisation and queueing.



\---



\## Repository



| path | |

|---|---|

| `src/streamguard/generator/` | synthetic transactions and fraud injection |

| `src/streamguard/eventlog/` | file-backed append-only log |

| `src/streamguard/features/` | 58-feature engine, no look-ahead |

| `src/streamguard/ml/` | split, metrics, training, SHAP, drift, costs |

| `src/streamguard/api/` | FastAPI service, decisions, cases, auth |

| `frontend/` | React console - live stream, case queue, risk dashboard |

| `scripts/` | build, train, diagnose, benchmark |

| `tests/` | 158 tests |

| `docs/PROJECT\_RECORD.md` | full build log, every number and decision |



\---



\## Limitations



\- Synthetic data, separable by design. The numbers describe the generator.

\- 62 req/sec on one worker. Horizontal scaling needs a durable state store.

\- Users are in-memory with development passwords; a real deployment uses

&#x20; an identity provider.

\- `ring\_size` graph feature failed - devices are assigned randomly, so

&#x20; there are no fraud rings to detect.

\- CI runs 104 of 158 tests; the rest need PostgreSQL or the feature file.

