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

from fastapi import FastAPI, HTTPException, Request, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse

from streamguard.api.schemas import (
    ScoreRequest, ScoreResponse, HealthResponse, FORBIDDEN_FIELDS,
)
from streamguard.api.scorer import Scorer, ScorerConfig
from streamguard.api.cases import CaseRepository, Verdict, CaseStatus
from streamguard.api.auth import (
    UserStore, Role, create_token, decode_token, verify_configuration,
    TokenData,
)
from pydantic import BaseModel, Field
from streamguard.ml.splitter import PROJECT_ROOT
from streamguard.utils.logging_config import get_logger, setup_logging

log = get_logger(__name__)

MODEL_TAG = os.getenv("STREAMGUARD_MODEL", "lgbm_v6")
WARM_EVENTS = int(os.getenv("STREAMGUARD_WARM_EVENTS", "0"))

_scorer: Scorer | None = None
_cases = CaseRepository()
_users = UserStore()
_bearer = HTTPBearer(auto_error=False)


def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> TokenData:
    """Verify the bearer token. 401 if missing, invalid or expired."""
    if creds is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "missing bearer token",
            headers={"WWW-Authenticate": "Bearer"})

    data = decode_token(creds.credentials)
    if data is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"})
    return data


def require(permission: str):
    """Dependency factory: 403 unless the caller holds this permission.

    403, not 404: the caller IS authenticated, they simply may not do
    this. Hiding the endpoint's existence would be security through
    obscurity and would make a legitimate permissions bug look like a
    routing bug.
    """
    def check(user: TokenData = Depends(current_user)) -> TokenData:
        if not user.can(permission):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"role '{user.role}' may not '{permission}'")
        return user
    return check


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=72)

class AssignRequest(BaseModel):
    # No `analyst` field: the identity comes from the verified token,
    # not from the request body. A caller must not be able to act as
    # someone else.
    pass


class VerdictRequest(BaseModel):
    verdict: str = Field(..., description=str(sorted(Verdict.ALL)))
    notes: str = Field(default="", max_length=4000)


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
    cfg = verify_configuration()
    log.info("auth_configured", **cfg)

    # Seed users. A real deployment uses the bank's identity provider;
    # these exist so the authorisation model can be exercised.
    _users.add(os.getenv("SG_ANALYST_USER", "analyst"),
               os.getenv("SG_ANALYST_PASS", "analyst-dev-password"),
               Role.ANALYST)
    _users.add(os.getenv("SG_MANAGER_USER", "manager"),
               os.getenv("SG_MANAGER_PASS", "manager-dev-password"),
               Role.RISK_MANAGER)
    _users.add(os.getenv("SG_SERVICE_USER", "payment-switch"),
               os.getenv("SG_SERVICE_PASS", "switch-dev-password"),
               Role.SERVICE)
    log.info("users_seeded", n=len(_users.users))

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
def score(req: ScoreRequest, persist: bool = True,
          user: TokenData = Depends(require("score"))) -> ScoreResponse:
    """Score one transaction, and persist the decision.

    The request schema forbids extra fields, so a client cannot send
    is_fraud or fraud_type. That is enforced by Pydantic before this
    function runs - see schemas.FORBIDDEN_FIELDS.

    Persisting is best-effort: a database problem must not stop an
    authorisation decision being returned. The failure is logged.
    """
    s = get_scorer()
    try:
        result = s.score(req.to_payload())
    except Exception as exc:
        log.error("scoring_failed", ref=req.transaction_ref, error=str(exc))
        raise HTTPException(500, f"scoring failed: {exc}")

    if persist and not result.get("duplicate"):
        try:
            payload = req.to_payload()
            # Store ALL features the model saw, base + graph. The
            # Task 4B note was explicit: features are stored as JSONB
            # so training/serving skew can be DETECTED later, and you
            # can only detect it if you recorded it. Recording 49 of
            # 58 would leave the graph features unverifiable.
            base = s.computer.compute_features(payload)
            graph = s.graph.compute(
                str(payload["card_ref"]), str(payload["merchant_ref"]),
                str(payload["device_ref"]) if payload.get("device_ref") else None,
                req.occurred_at,
            )
            _cases.record_decision(req.transaction_ref, result,
                                   {**base, **graph})
        except Exception as exc:
            log.error("persist_failed", ref=req.transaction_ref,
                      error=str(exc))

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
# ---------------------------------------------------------------------
#  Task 22 - case management
# ---------------------------------------------------------------------

@app.get("/cases")
def list_cases(limit: int = 50, status: str = CaseStatus.OPEN,
               assigned_to: str | None = None,
               user: TokenData = Depends(require("read_cases"))) -> dict:
    """The analyst queue, most urgent first.

    Priority is score x amount, not score alone: a 0.95 on a Rs 50
    card-testing probe matters less than a 0.40 on Rs 200,000.
    """
    cases = _cases.queue(limit=limit, status=status,
                         assigned_to=assigned_to)
    return {"count": len(cases), "status": status,
            "cases": [c.to_dict() for c in cases]}


@app.get("/cases/{case_ref}")
def get_case(case_ref: str,
             user: TokenData = Depends(require("read_cases"))) -> dict:
    """One case with its SHAP explanation and full audit trail."""
    case = _cases.get(case_ref)
    if case is None:
        raise HTTPException(404, f"case {case_ref} not found")
    return case


@app.post("/cases/{case_ref}/assign")
def assign_case(case_ref: str, req: AssignRequest,
                user: TokenData = Depends(require("assign_case"))) -> dict:
    # The VERIFIED identity, not the one the caller claimed. Before
    # this task the audit trail recorded whatever actor the request
    # body said, which is not an audit trail.
    result = _cases.assign(case_ref, user.username)
    if not result.get("ok"):
        raise HTTPException(400, result.get("reason", "assign failed"))
    return result


@app.post("/cases/{case_ref}/verdict")
def submit_verdict(case_ref: str, req: VerdictRequest,
                   user: TokenData = Depends(require("submit_verdict"))) -> dict:
    """Close a case with the analyst's conclusion.

    This verdict is the label Task 30 retrains on. 'inconclusive' is
    recorded but NOT usable as a label - an analyst who could not
    decide has not said the transaction was legitimate.
    """
    result = _cases.submit_verdict(case_ref, user.username,
                                   req.verdict, req.notes)
    if not result.get("ok"):
        raise HTTPException(400, result.get("reason", "verdict failed"))
    return result


@app.get("/cases-stats")
def case_stats(user: TokenData = Depends(require("read_stats"))) -> dict:
    """Decision counts, case states, and how many labels exist."""
    return _cases.stats()
@app.post("/auth/token")
def login(req: LoginRequest) -> dict:
    """Exchange a username and password for a bearer token."""
    user = _users.authenticate(req.username, req.password)
    if user is None:
        log.info("login_failed", username=req.username)
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "invalid credentials",
            headers={"WWW-Authenticate": "Bearer"})
    log.info("login_ok", username=user.username, role=user.role)
    return create_token(user)


@app.get("/auth/me")
def whoami(user: TokenData = Depends(current_user)) -> dict:
    """Who does the server think you are, and what may you do?"""
    from streamguard.api.auth import PERMISSIONS
    return {"username": user.username, "role": user.role,
            "permissions": sorted(PERMISSIONS.get(user.role, [])),
            "expires_at": user.expires_at.isoformat()}