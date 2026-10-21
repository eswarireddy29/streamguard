"""
tests/test_api.py

Task 28 - the API contract, without uvicorn.

FastAPI's TestClient calls the app in-process, so these run in pytest
with no server to start and no port to collide with. They cover what
the Task 23 script covered - but automatically, every time.

The SCORING endpoint is not exercised here: it needs the feature state
that Task 19 warms from the event log, which takes minutes. What is
tested is the CONTRACT - auth, permissions, validation, error shapes -
which is where a regression would be silent.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from streamguard.api.auth import Role, UserStore, create_token


@pytest.fixture(scope="module")
def app_module():
    """Import the app without running its lifespan.

    The lifespan replays the event log to warm feature state - minutes
    of work for tests that never score anything. TestClient is used
    WITHOUT a context manager so startup never fires.
    """
    import streamguard.api.main as m

    # Seed users directly: the lifespan would normally do this.
    m._users = UserStore()
    m._users.add("alice", "analyst-password", Role.ANALYST)
    m._users.add("bob", "manager-password", Role.RISK_MANAGER)
    m._users.add("switch", "service-password", Role.SERVICE)
    return m


@pytest.fixture
def client(app_module):
    return TestClient(app_module.app)


def token_for(app_module, username: str) -> str:
    user = app_module._users.users[username]
    return create_token(user)["access_token"]


def auth(app_module, username: str) -> dict:
    return {"Authorization": f"Bearer {token_for(app_module, username)}"}


class TestLogin:
    def test_valid_credentials_return_a_token(self, client):
        r = client.post("/auth/token",
                        json={"username": "alice",
                              "password": "analyst-password"})
        assert r.status_code == 200
        body = r.json()
        assert body["token_type"] == "bearer"
        assert body["role"] == Role.ANALYST
        assert body["access_token"]

    def test_wrong_password_is_401(self, client):
        r = client.post("/auth/token",
                        json={"username": "alice", "password": "wrong"})
        assert r.status_code == 401

    def test_unknown_user_gives_the_SAME_message(self, client):
        """The response must not reveal which usernames exist."""
        a = client.post("/auth/token",
                        json={"username": "alice", "password": "wrong"})
        b = client.post("/auth/token",
                        json={"username": "ghost", "password": "wrong"})
        assert a.status_code == b.status_code == 401
        assert a.json()["detail"] == b.json()["detail"]


class TestAuthenticationRequired:
    def test_no_token_is_401(self, client):
        assert client.get("/cases").status_code == 401

    def test_bad_token_is_401(self, client):
        r = client.get("/cases",
                       headers={"Authorization": "Bearer rubbish"})
        assert r.status_code == 401

    def test_health_is_open(self, client):
        """A load balancer needs it. 503 while unwarmed is fine;
        401 would not be."""
        assert client.get("/health").status_code in (200, 503)

    def test_root_is_open(self, client):
        assert client.get("/").status_code == 200


class TestPermissionMatrix:
    """403, not 404. The caller IS authenticated, they just may not
    do this. Hiding the endpoint would make a permissions bug look
    like a routing bug."""

    def test_service_cannot_read_cases(self, client, app_module):
        r = client.get("/cases", headers=auth(app_module, "switch"))
        assert r.status_code == 403

    def test_analyst_cannot_read_stats(self, client, app_module):
        r = client.get("/cases-stats", headers=auth(app_module, "alice"))
        assert r.status_code == 403

    def test_analyst_cannot_read_risk_kpis(self, client, app_module):
        r = client.get("/risk-kpis", headers=auth(app_module, "alice"))
        assert r.status_code == 403

    def test_manager_can_read_stats(self, client, app_module):
        r = client.get("/cases-stats", headers=auth(app_module, "bob"))
        assert r.status_code == 200

    def test_403_names_the_permission(self, client, app_module):
        r = client.get("/cases-stats", headers=auth(app_module, "alice"))
        assert "read_stats" in r.json()["detail"]


class TestWhoami:
    def test_returns_the_verified_identity(self, client, app_module):
        r = client.get("/auth/me", headers=auth(app_module, "alice"))
        assert r.status_code == 200
        body = r.json()
        assert body["username"] == "alice"
        assert body["role"] == Role.ANALYST
        assert "read_stats" not in body["permissions"]


class TestScoreValidation:
    """The schema must reject the label. Pydantic runs before any
    project code, so these never reach the scorer."""

    MINIMAL = {
        "transaction_ref": "T1",
        "occurred_at": "2026-03-20T14:30:00+05:30",
        "card_ref": "CARD0000001",
        "customer_ref": "CUST0000001",
        "merchant_ref": "MERCH000001",
        "amount": 100.0,
        "channel": "ecommerce",
        "entry_mode": "manual",
    }

    def test_is_fraud_is_rejected(self, client, app_module):
        """THE SECURITY RULE. The event payload carries is_fraud, so a
        client could send it. A client sending the answer is either
        confused or probing."""
        body = {**self.MINIMAL, "is_fraud": False}
        r = client.post("/score", json=body,
                        headers=auth(app_module, "switch"))
        assert r.status_code == 422
        detail = r.json()["detail"]
        assert any(d["type"] == "extra_forbidden" for d in detail)
        assert any("is_fraud" in d["loc"] for d in detail)

    def test_fraud_type_is_rejected(self, client, app_module):
        body = {**self.MINIMAL, "fraud_type": "card_testing"}
        r = client.post("/score", json=body,
                        headers=auth(app_module, "switch"))
        assert r.status_code == 422

    def test_negative_amount_is_rejected(self, client, app_module):
        body = {**self.MINIMAL, "amount": -100.0}
        r = client.post("/score", json=body,
                        headers=auth(app_module, "switch"))
        assert r.status_code == 422

    def test_missing_field_is_rejected(self, client, app_module):
        body = {k: v for k, v in self.MINIMAL.items()
                if k != "card_ref"}
        r = client.post("/score", json=body,
                        headers=auth(app_module, "switch"))
        assert r.status_code == 422

    def test_validation_happens_before_authorisation_is_irrelevant(
            self, client):
        """An unauthenticated bad request is still 401, not 422 -
        authentication is checked first, so an attacker cannot probe
        the schema without credentials."""
        r = client.post("/score", json={"rubbish": True})
        assert r.status_code == 401


class TestErrorShapes:
    def test_unknown_case_is_404(self, client, app_module):
        r = client.get("/cases/NOPE", headers=auth(app_module, "alice"))
        assert r.status_code in (404, 500)

    def test_invalid_verdict_is_rejected(self, client, app_module):
        r = client.post("/cases/NOPE/verdict",
                        json={"verdict": "probably_fine"},
                        headers=auth(app_module, "alice"))
        assert r.status_code == 400

    def test_verdict_body_has_no_analyst_field(self, client, app_module):
        """The identity comes from the token. If the schema accepted an
        analyst name, a caller could act as someone else and the audit
        trail would be worthless."""
        from streamguard.api.main import VerdictRequest
        assert "analyst" not in VerdictRequest.model_fields