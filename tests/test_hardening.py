"""
tests/test_hardening.py

Task 29 - the error-handling fixes, as PASS/FAIL.

Each test here corresponds to a problem the Task 29 probe actually
found. Writing tests for imagined problems is guessing; these are
regressions waiting to happen.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from streamguard.api.auth import Role, UserStore, create_token
from streamguard.api.schemas import ScoreRequest


@pytest.fixture(scope="module")
def app_module():
    import streamguard.api.main as m
    m._users = UserStore()
    m._users.add("alice", "analyst-password", Role.ANALYST)
    m._users.add("bob", "manager-password", Role.RISK_MANAGER)
    m._users.add("switch", "service-password", Role.SERVICE)
    return m


@pytest.fixture
def client(app_module):
    return TestClient(app_module.app, raise_server_exceptions=False)


def auth(app_module, username: str) -> dict:
    user = app_module._users.users[username]
    return {"Authorization": f"Bearer {create_token(user)['access_token']}"}


BASE = {
    "transaction_ref": "T1",
    "occurred_at": "2026-03-20T14:30:00+05:30",
    "card_ref": "C1",
    "customer_ref": "CU1",
    "merchant_ref": "M1",
    "channel": "ecommerce",
    "entry_mode": "manual",
}


class TestQueryParameterBounds:
    """FOUND BY THE PROBE: an unvalidated limit reached SQL and
    produced 'LIMIT must not be negative' - a 500 with the full query
    and its parameters in the log."""

    def test_negative_limit_is_422_not_500(self, client, app_module):
        r = client.get("/cases?limit=-1", headers=auth(app_module, "alice"))
        assert r.status_code == 422

    def test_zero_limit_is_rejected(self, client, app_module):
        r = client.get("/cases?limit=0", headers=auth(app_module, "alice"))
        assert r.status_code == 422

    def test_enormous_limit_is_rejected(self, client, app_module):
        """Without an upper bound one request reads the whole table."""
        r = client.get("/cases?limit=99999999",
                       headers=auth(app_module, "alice"))
        assert r.status_code == 422

    def test_unknown_status_is_rejected(self, client, app_module):
        r = client.get("/cases?status=../../etc/passwd",
                       headers=auth(app_module, "alice"))
        assert r.status_code == 422

    def test_valid_status_values_still_work(self, client, app_module):
        for s in ("open", "in_review", "closed"):
            r = client.get(f"/cases?status={s}",
                           headers=auth(app_module, "alice"))
            assert r.status_code == 200

    def test_negative_since_id_is_rejected(self, client, app_module):
        r = client.get("/recent-decisions?since_id=-5",
                       headers=auth(app_module, "alice"))
        assert r.status_code == 422

    def test_negative_cost_is_rejected(self, client, app_module):
        """A negative cost would invert the threshold maths."""
        r = client.get("/risk-kpis?fn_cost=-1",
                       headers=auth(app_module, "bob"))
        assert r.status_code == 422


class TestFiniteNumbers:
    """FOUND BY THE PROBE: NaN produced a 500. Task 10 guarantees zero
    NaN/inf in the feature vector; this enforces it at the boundary."""

    @pytest.mark.parametrize("value", [float("nan"), float("inf"),
                                       float("-inf")])
    def test_non_finite_amount_is_rejected(self, value):
        with pytest.raises(Exception):
            ScoreRequest(**{**BASE, "amount": value})

    @pytest.mark.parametrize("value", [float("nan"), float("inf")])
    def test_non_finite_coordinates_are_rejected(self, value):
        with pytest.raises(Exception):
            ScoreRequest(**{**BASE, "amount": 100.0, "lat": value})

    def test_ordinary_values_still_pass(self):
        req = ScoreRequest(**{**BASE, "amount": 100.0, "lat": 26.9,
                              "lon": 75.8})
        assert req.amount == 100.0

    def test_nan_in_the_body_is_400_not_500(self, client, app_module):
        """NaN is not valid JSON, so the parser raises before Pydantic
        sees it. A malformed body is the caller's problem - 400, not a
        500 that tells an operator to investigate."""
        import json
        body = json.dumps({**BASE, "amount": float("nan")})
        r = client.post("/score", content=body.encode(),
                        headers={**auth(app_module, "switch"),
                                 "Content-Type": "application/json"})
        assert r.status_code == 400


class TestBoundedStrings:
    """FOUND BY THE PROBE: free-text fields had no length limit. An
    unbounded string is a memory risk and hits a column limit later."""

    def test_oversized_city_is_rejected(self):
        with pytest.raises(Exception):
            ScoreRequest(**{**BASE, "amount": 100.0, "city": "X" * 100_000})

    def test_oversized_merchant_category_is_rejected(self):
        with pytest.raises(Exception):
            ScoreRequest(**{**BASE, "amount": 100.0,
                            "merchant_category": "X" * 100_000})

    def test_ordinary_city_names_pass(self):
        for city in ("Jaipur", "Thiruvananthapuram", "São Paulo"):
            req = ScoreRequest(**{**BASE, "amount": 100.0, "city": city})
            assert req.city == city


class TestNoInternalLeakage:
    """An error body must say nothing an attacker can use. The log
    keeps the detail for an operator."""

    FORBIDDEN = ("Traceback", "sqlalchemy", "psycopg", "StreamGuard2026",
                 "streamguard/", 'File "')

    def test_404_body_is_clean(self, client, app_module):
        r = client.get("/cases/NOPE", headers=auth(app_module, "alice"))
        for word in self.FORBIDDEN:
            assert word not in r.text

    def test_422_body_is_clean(self, client, app_module):
        r = client.get("/cases?limit=-1", headers=auth(app_module, "alice"))
        for word in self.FORBIDDEN:
            assert word not in r.text

    def test_401_body_is_clean(self, client):
        r = client.get("/cases", headers={"Authorization": "Bearer bad"})
        for word in self.FORBIDDEN:
            assert word not in r.text

    def test_database_password_never_appears(self, client, app_module):
        """The password is in .env and settings. It must never reach a
        response, whatever goes wrong."""
        for path in ("/cases/NOPE", "/cases?limit=-1", "/no-such-route"):
            r = client.get(path, headers=auth(app_module, "alice"))
            assert "StreamGuard2026" not in r.text


class TestMalformedBodies:
    def test_broken_json(self, client, app_module):
        r = client.post("/score", content=b"{not json",
                        headers={**auth(app_module, "switch"),
                                 "Content-Type": "application/json"})
        assert r.status_code in (400, 422)

    def test_array_instead_of_object(self, client, app_module):
        r = client.post("/score", json=[],
                        headers=auth(app_module, "switch"))
        assert r.status_code == 422

    def test_sql_in_a_path_parameter_is_harmless(self, client, app_module):
        """Parameterised queries make this a lookup that finds nothing,
        not an injection."""
        r = client.get("/cases/'; DROP TABLE cases; --",
                       headers=auth(app_module, "alice"))
        assert r.status_code in (404, 422)

    def test_cases_table_still_exists_afterwards(self, client, app_module):
        r = client.get("/cases", headers=auth(app_module, "alice"))
        assert r.status_code == 200