"""
src/streamguard/api/auth.py

Task 23 - who is calling, and what are they allowed to do?

Until now anyone who could reach port 8000 could block a card or close
a case as any analyst. The Task 22 audit trail recorded an `actor`
field that the caller supplied about themselves - which is not an
audit trail, it is a suggestion box.

THREE ROLES, because three different jobs touch this system:

  analyst       works the queue, submits verdicts. Cannot change
                thresholds or block cards - those are policy.
  risk_manager  everything an analyst can do, plus the policy lists
                and thresholds. Cannot see raw card data.
  service       the payment switch calling /score. Can ONLY score.
                A compromised switch credential must not be able to
                close cases or read the queue.

JWT, not sessions: the scoring service is stateless by design (Task
19 Option A keeps feature state, not user state), and a token the
server does not have to look up is one fewer thing in the hot path.

SECRET HANDLING: the key comes from the environment. A hardcoded
default exists for local development and the service REFUSES TO START
with it if the environment says production - a dev convenience that
silently becomes a production hole is how this goes wrong.
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from streamguard.utils.logging_config import get_logger

log = get_logger(__name__)

ALGORITHM = "HS256"
TOKEN_MINUTES = int(os.getenv("STREAMGUARD_TOKEN_MINUTES", "60"))

# Development default. See the check in verify_configuration() below.
DEV_SECRET = "streamguard-dev-secret-do-not-use-in-production"
SECRET = os.getenv("STREAMGUARD_JWT_SECRET", DEV_SECRET)
ENVIRONMENT = os.getenv("STREAMGUARD_ENV", "development")

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


class Role:
    ANALYST = "analyst"
    RISK_MANAGER = "risk_manager"
    SERVICE = "service"

    ALL = {ANALYST, RISK_MANAGER, SERVICE}


# What each role may do. Listing permissions explicitly beats checking
# role names at each endpoint: a new role is a new row here, not a
# scattered set of `if role == ...` conditions to find and update.
PERMISSIONS: dict = {
    Role.SERVICE: {"score"},
    Role.ANALYST: {"score", "read_cases", "assign_case", "submit_verdict"},
    Role.RISK_MANAGER: {"score", "read_cases", "assign_case",
                        "submit_verdict", "manage_policy", "read_stats"},
}


@dataclass
class User:
    username: str
    role: str
    password_hash: str
    disabled: bool = False

    def can(self, permission: str) -> bool:
        return permission in PERMISSIONS.get(self.role, set())


@dataclass
class TokenData:
    """What a verified token tells us about the caller."""
    username: str
    role: str
    expires_at: datetime

    def can(self, permission: str) -> bool:
        return permission in PERMISSIONS.get(self.role, set())


class UserStore:
    """In-memory users.

    A real deployment would use the identity provider the bank already
    has. The point of this task is the authorisation model - which role
    may do what, and that the audit trail records a VERIFIED identity
    rather than a self-declared one.
    """

    def __init__(self):
        self.users: dict = {}

    def add(self, username: str, password: str, role: str) -> User:
        if role not in Role.ALL:
            raise ValueError(f"role must be one of {sorted(Role.ALL)}")
        # bcrypt truncates above 72 bytes and raises on longer input,
        # so the limit is enforced here rather than discovered later.
        if len(password.encode()) > 72:
            raise ValueError("password must be 72 bytes or fewer")
        u = User(username=username, role=role,
                 password_hash=pwd.hash(password))
        self.users[username] = u
        return u

    def authenticate(self, username: str, password: str) -> User | None:
        u = self.users.get(username)
        if u is None:
            # Hash anyway, so a missing username and a wrong password
            # take the same time. Otherwise the response time tells an
            # attacker which usernames exist.
            pwd.hash("timing-equalizer")
            return None
        if u.disabled:
            return None
        if not pwd.verify(password, u.password_hash):
            return None
        return u


def create_token(user: User, minutes: int = TOKEN_MINUTES) -> dict:
    """Issue a signed token carrying the username and role."""
    expires = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    payload = {
        "sub": user.username,
        "role": user.role,
        "exp": expires,
        "iat": datetime.now(timezone.utc),
        # A unique id per token, so a specific token can be revoked
        # later without invalidating every token the user holds.
        "jti": secrets.token_urlsafe(16),
    }
    token = jwt.encode(payload, SECRET, algorithm=ALGORITHM)
    return {"access_token": token, "token_type": "bearer",
            "expires_in": minutes * 60, "role": user.role}


def decode_token(token: str) -> TokenData | None:
    """Verify a token. Returns None for anything not valid.

    Signature and expiry are both checked by jose. An expired token
    fails here, which is why the expiry is short by default - a stolen
    token is useful for minutes, not forever.
    """
    try:
        payload = jwt.decode(token, SECRET, algorithms=[ALGORITHM])
    except JWTError as exc:
        log.info("token_rejected", error=str(exc))
        return None

    username = payload.get("sub")
    role = payload.get("role")
    if not username or role not in Role.ALL:
        return None

    return TokenData(
        username=username, role=role,
        expires_at=datetime.fromtimestamp(payload["exp"], tz=timezone.utc),
    )


def verify_configuration() -> dict:
    """Refuse to run in production with the development secret.

    A dev default that silently survives into production is one of the
    most common ways a service ends up with a forgeable token. This
    makes it loud at startup instead of silent forever.
    """
    using_dev = SECRET == DEV_SECRET
    is_prod = ENVIRONMENT.lower() in ("production", "prod")

    if using_dev and is_prod:
        raise RuntimeError(
            "STREAMGUARD_JWT_SECRET is still the development default "
            "while STREAMGUARD_ENV is production. Set a real secret."
        )

    if using_dev:
        log.warning("using_development_jwt_secret",
                    hint="set STREAMGUARD_JWT_SECRET before deploying")

    return {"environment": ENVIRONMENT,
            "using_dev_secret": using_dev,
            "token_minutes": TOKEN_MINUTES,
            "algorithm": ALGORITHM}