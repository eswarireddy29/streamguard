"""
src/streamguard/ml/tracking.py

Task 18C - MLflow experiment tracking, local file backend.

Eight model versions exist across Tasks 13-18 and their results sit in
separate JSON files. That works while the project is fresh. It stops
working at Task 30, when retraining from analyst labels has to answer
"is this better than what is deployed?" - a question you cannot settle
by comparing a number on screen against a file from three weeks ago.

MLflow stores runs in ./mlruns as plain files. No server, no database,
no cost. The UI reads the same folder.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import mlflow

from streamguard.ml.splitter import PROJECT_ROOT
from streamguard.utils.logging_config import get_logger

log = get_logger(__name__)

MLRUNS = PROJECT_ROOT / "mlruns"
EXPERIMENT = "streamguard-fraud"


def configure(experiment: str = EXPERIMENT) -> str:
    """Point MLflow at the local folder and select the experiment.

    A file URI rather than a tracking server: nothing to run, nothing
    to keep alive, and the whole history is in the repo folder.
    """
    MLRUNS.mkdir(parents=True, exist_ok=True)
    mlflow.set_tracking_uri(MLRUNS.as_uri())
    mlflow.set_experiment(experiment)
    return MLRUNS.as_uri()


@dataclass
class RunRecord:
    """One logged run, for the console summary."""
    name: str
    run_id: str
    metrics: dict
    params: dict


def log_run(name: str, params: dict, metrics: dict,
            artifacts: list | None = None,
            tags: dict | None = None) -> RunRecord:
    """Log one model version.

    params  - what was CHOSEN (hyperparameters, feature count, strategy)
    metrics - what was MEASURED (PR-AUC, gap, per-pattern recall)
    The distinction matters: you search over params to improve metrics,
    and mixing them makes the history unreadable.
    """
    with mlflow.start_run(run_name=name) as run:
        clean_params = {k: v for k, v in params.items() if v is not None}
        mlflow.log_params(clean_params)

        flat = {}
        for k, v in metrics.items():
            if isinstance(v, dict):
                for kk, vv in v.items():
                    if isinstance(vv, (int, float)):
                        flat[f"{k}_{kk}"] = float(vv)
            elif isinstance(v, (int, float)):
                flat[k] = float(v)
        mlflow.log_metrics(flat)

        if tags:
            mlflow.set_tags(tags)

        for a in (artifacts or []):
            p = Path(a)
            if p.exists():
                mlflow.log_artifact(str(p))

        log.info("mlflow_run_logged", name=name, run_id=run.info.run_id,
                 metrics=len(flat), params=len(clean_params))
        return RunRecord(name=name, run_id=run.info.run_id,
                         metrics=flat, params=clean_params)


def load_report(path: Path) -> dict:
    """Read one of the task report JSON files."""
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))