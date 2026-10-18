"""
Verify the database connection.

    python scripts/check_db.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from streamguard.config.settings import settings  # noqa: E402
from streamguard.db.session import (  # noqa: E402
    check_connection,
    get_server_info,
    get_session,
)
from streamguard.utils.logging_config import get_logger, setup_logging  # noqa: E402
from sqlalchemy import text  # noqa: E402


def main() -> None:
    setup_logging()
    log = get_logger(__name__)

    print("\n" + "=" * 62)
    print("  STREAMGUARD — DATABASE CHECK")
    print("=" * 62)

    print(f"\n  Target : {settings.postgres_host}:{settings.postgres_port}"
          f"/{settings.postgres_db}")
    print(f"  User   : {settings.postgres_user}")

    print("\n  Connecting...")
    if not check_connection():
        print("\n  FAILED — could not reach the database.")
        print("  Check: is the postgresql service running?")
        print("         does POSTGRES_PASSWORD in .env match the installer?")
        print("         was the 'streamguard' database created?\n")
        sys.exit(1)

    print("  OK — connection established.\n")

    info = get_server_info()
    print(f"  Database : {info['database']}")
    print(f"  User     : {info['user']}")
    print(f"  Version  : {info['version'][:60]}...")

    print("\n  Testing a write/read cycle...")
    with get_session() as db:
        db.execute(text(
            "CREATE TABLE IF NOT EXISTS _connection_test "
            "(id SERIAL PRIMARY KEY, note TEXT)"
        ))
        db.execute(text(
            "INSERT INTO _connection_test (note) VALUES (:n)"
        ), {"n": "streamguard connectivity check"})

    with get_session() as db:
        count = db.execute(
            text("SELECT COUNT(*) FROM _connection_test")
        ).scalar_one()
        print(f"  OK — rows in test table: {count}")
        db.execute(text("DROP TABLE _connection_test"))
        print("  OK — test table cleaned up.")

    print("\n" + "=" * 62)
    log.info("database_check_passed", database=info["database"])
    print("\n  Database is ready.\n")


if __name__ == "__main__":
    main()