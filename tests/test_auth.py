"""
tests/test_auth.py

Task 28 - tokens and permissions, without a server.

Task 23 verified these over HTTP against a running uvicorn. That is an
integration test and a slow one. The authorisation MODEL - which role
may do what, whether a token survives tampering - is pure logic and
belongs in a fast test that runs on every change.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt

from streamguard.api.auth import (
    ALGORITHM, PERMISSIONS, Role, SECRET, UserStore,
    create_token, decode_token, verify_configuration,
)


@pytest.fixture
def store():
    s = UserStore()
    s.add("alice", "analyst-password", Role.ANALYST)
    s.add("bob", "manager-password", Role.RISK_MANAGER)
    s.add("switch", "service-password", Role.SERVICE)
    return s


class TestAuthentication:
    def test_correct_password_authenticates(self, store):
        assert store.authenticate("alice", "analyst-password") is not None

    def test_wrong_password_fails(self, store):
        assert store.authenticate("alice", "wrong") is None

    def test_unknown_user_fails(self, store):
        assert store.authenticate("ghost", "anything") is None

    def test_password_is_hashed_not_stored(self, store):
        """A password visible in memory is a password in a crash dump."""
        u = store.users["alice"]
        assert u.password_hash != "analyst-password"
        assert u.password_hash.startswith("$2")

    def test_disabled_user_cannot_authenticate(self, store):
        store.users["alice"].disabled = True
        assert store.authenticate("alice", "analyst-password") is None

    def test_long_password_rejected_at_the_boundary(self, store):
        """bcrypt raises above 72 bytes. Enforce it where the password
        enters the system, not where it reaches the hasher."""
        with pytest.raises(ValueError):
            store.add("carol", "x" * 100, Role.ANALYST)

    def test_invalid_role_rejected(self, store):
        with pytest.raises(ValueError):
            store.add("dave", "password", "superuser")


class TestTokens:
    def test_round_trip(self, store):
        u = store.authenticate("alice", "analyst-password")
        token = create_token(u)["access_token"]
        data = decode_token(token)
        assert data.username == "alice"
        assert data.role == Role.ANALYST

    def test_garbage_is_rejected(self):
        assert decode_token("not-a-token") is None

    def test_tampered_token_is_rejected(self, store):
        """THE DECISIVE TEST. Change one character and the signature
        no longer matches. Without this check anyone could mint a
        risk_manager token."""
        u = store.authenticate("alice", "analyst-password")
        token = create_token(u)["access_token"]
        head, body, sig = token.split(".")
        tampered = f"{head}.{body}.{sig[:-2]}XY"
        assert decode_token(tampered) is None

    def test_token_signed_with_another_secret_is_rejected(self):
        payload = {
            "sub": "attacker", "role": Role.RISK_MANAGER,
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        forged = jwt.encode(payload, "a-different-secret",
                            algorithm=ALGORITHM)
        assert decode_token(forged) is None

    def test_expired_token_is_rejected(self, store):
        u = store.authenticate("alice", "analyst-password")
        token = create_token(u, minutes=-1)["access_token"]
        assert decode_token(token) is None

    def test_unknown_role_in_a_valid_token_is_rejected(self):
        """Correctly signed but claiming a role that does not exist."""
        payload = {
            "sub": "alice", "role": "superuser",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        token = jwt.encode(payload, SECRET, algorithm=ALGORITHM)
        assert decode_token(token) is None

    def test_tokens_are_unique(self, store):
        """A jti per token means one can be revoked without
        invalidating every token the user holds."""
        u = store.authenticate("alice", "analyst-password")
        a = create_token(u)["access_token"]
        b = create_token(u)["access_token"]
        assert a != b


class TestPermissions:
    def test_service_can_only_score(self):
        """The payment switch calls /score thousands of times a day,
        so its credential is the most exposed. A compromised switch
        key must not reach the analyst queue."""
        assert PERMISSIONS[Role.SERVICE] == {"score"}

    def test_analyst_cannot_read_stats(self):
        assert "read_stats" not in PERMISSIONS[Role.ANALYST]

    def test_analyst_cannot_manage_policy(self):
        """Blocking a card is a risk decision, not an analyst one."""
        assert "manage_policy" not in PERMISSIONS[Role.ANALYST]

    def test_risk_manager_has_everything_an_analyst_has(self):
        assert PERMISSIONS[Role.ANALYST] <= PERMISSIONS[Role.RISK_MANAGER]

    def test_every_role_is_defined(self):
        assert set(PERMISSIONS) == Role.ALL

    def test_token_data_can_check_permissions(self, store):
        u = store.authenticate("switch", "service-password")
        data = decode_token(create_token(u)["access_token"])
        assert data.can("score")
        assert not data.can("read_cases")


class TestConfiguration:
    def test_configuration_reports_its_state(self):
        cfg = verify_configuration()
        assert cfg["algorithm"] == ALGORITHM
        assert cfg["token_minutes"] > 0

    def test_dev_secret_is_flagged(self):
        """It is allowed in development and must be loud about it.
        A dev default that silently survives into production is how a
        service ends up with forgeable tokens."""
        cfg = verify_configuration()
        assert "using_dev_secret" in cfg