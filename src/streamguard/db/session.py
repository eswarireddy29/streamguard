"""
Database connection management.

One engine per process, one session per unit of work.
"""

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from streamguard.config.settings import settings
from streamguard.utils.logging_config import get_logger

log = get_logger(__name__)

# The engine manages a POOL of connections, reused across requests.
# Opening a new connection per query would be far too slow for a
# service with a latency budget.
engine: Engine = create_engine(
    settings.database_url,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    echo=False,
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    class_=Session,
)


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """
    Provide a transactional session.

    Commits on success, rolls back on any exception, always closes.

        with get_session() as db:
            db.add(transaction)
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        log.exception("database_session_rolled_back")
        raise
    finally:
        session.close()


def check_connection() -> bool:
    """Return True if the database is reachable."""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            return result.scalar() == 1
    except Exception as exc:
        log.error("database_connection_failed", error=str(exc))
        return False


def get_server_info() -> dict[str, str]:
    """Fetch version and database name from the live server."""
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version()")).scalar_one()
        db_name = conn.execute(text("SELECT current_database()")).scalar_one()
        user = conn.execute(text("SELECT current_user")).scalar_one()
    return {"version": str(version), "database": str(db_name), "user": str(user)}