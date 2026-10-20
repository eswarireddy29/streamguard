"""
src/streamguard/api/main.py

Task 19 - the FastAPI scoring service.

    uvicorn streamguard.api.main:app --reload
    http://127.0.0.1:8000/docs

Startup replays the event log to rebuild feature state (Option A,
Task 19). That takes a few minutes on the full log; set
STREAMGUARD_WARM_EVENTS to a smaller number for quick iteration.
"""

from __future__ import annotations

import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from streamguard.api.schemas import (
    ScoreRequest, ScoreResponse, HealthResponse, FORBIDDEN_FIELDS,
)
from streamguard.api.scorer import Scorer, ScorerConfig
from streamguard.ml.splitter import PROJECT_ROOT
from streamguard.utils.logging_config import get_logger, setup_logging

log = get_logger(__name__)

MODEL_TAG = os.getenv("STREAMGUARD_MODEL", "lgbm_v6")
WARM_EVENTS = int(os.getenv("STREAMGUARD_WARM_EVENTS", "0"))

_scorer: Scorer | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Warm the feature state before accepting traffic.

    Scoring a transaction needs this card's history. Serving requests
    before the replay finishes would return scores computed from an
    empty state - wrong, and silently so.
    """
    global _scorer
    setup_logging()

    model_path = PROJECT_ROOT / "models" / f"{MODEL_TAG}.txt"
    if not model_path.exists():
        raise RuntimeError(f"model not found: {model_path}")

    log.info("startup", model=str(model_path), warm_events=WARM_EVENTS or "all")
    _scorer = Scorer(ScorerConfig(model_path=model_path,
                                  warm_events=WARM_EVENTS))
    _scorer.warm()
    log.info("ready", **_scorer.health())

    yield

    log.info("shutdown", scored=_scorer.scored if _scorer else 0)


app = FastAPI(
    title="StreamGuard",
    description="Real-time transaction fraud scoring",
    version="1.0.0",
    lifespan=lifespan,
)


def get_scorer() -> Scorer:
    if _scorer is None:
        raise HTTPException(503, "service is still warming up")
    return _scorer


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Is the service ready, and what is loaded?"""
    return HealthResponse(**get_scorer().health())


@app.post("/score", response_model=ScoreResponse)
def score(req: ScoreRequest) -> ScoreResponse:
    """Score one transaction.

    The request schema forbids extra fields, so a client cannot send
    is_fraud or fraud_type. That is enforced by Pydantic before this
    function runs - see schemas.FORBIDDEN_FIELDS.
    """
    s = get_scorer()
    try:
        result = s.score(req.to_payload())
    except Exception as exc:
        log.error("scoring_failed", ref=req.transaction_ref, error=str(exc))
        raise HTTPException(500, f"scoring failed: {exc}")

    return ScoreResponse(transaction_ref=req.transaction_ref, **result)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    """Never leak a stack trace to a caller."""
    log.error("unhandled", path=str(request.url.path), error=str(exc))
    return JSONResponse(status_code=500,
                        content={"detail": "internal error"})


@app.get("/")
def root() -> dict:
    return {
        "service": "StreamGuard",
        "docs": "/docs",
        "endpoints": ["/health", "/score"],
        "forbidden_request_fields": sorted(FORBIDDEN_FIELDS),
    }