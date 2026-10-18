"""
Verify configuration and logging are correctly wired.

Run from the project root:
    python scripts/check_config.py
"""

import sys
from pathlib import Path

# Make src/ importable without installing the package
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from streamguard.config.settings import PROJECT_ROOT, settings  # noqa: E402
from streamguard.utils.logging_config import get_logger, setup_logging  # noqa: E402


def main() -> None:
    setup_logging()
    log = get_logger(__name__)

    log.info("configuration_check_started", app=settings.app_name)

    print("\n" + "=" * 62)
    print("  STREAMGUARD — CONFIGURATION CHECK")
    print("=" * 62)

    print(f"\n  Project root : {PROJECT_ROOT}")
    print(f"  Environment  : {settings.app_env}")
    print(f"  Debug mode   : {settings.debug}")
    print(f"  Log level    : {settings.log_level}")

    print("\n  --- Database ---")
    print(f"  Host         : {settings.postgres_host}:{settings.postgres_port}")
    print(f"  Database     : {settings.postgres_db}")
    print(f"  User         : {settings.postgres_user}")
    masked = "*" * len(settings.postgres_password)
    print(f"  Password     : {masked}  (length {len(settings.postgres_password)})")

    print("\n  --- Simulation ---")
    print(f"  Customers    : {settings.n_customers:,}")
    print(f"  Merchants    : {settings.n_merchants:,}")
    print(f"  Days         : {settings.simulation_days}")
    print(f"  Fraud rate   : {settings.fraud_rate:.2%}")
    print(f"  Random seed  : {settings.random_seed}")

    print("\n  --- Thresholds & cost ---")
    print(f"  Review at    : {settings.score_threshold_review}")
    print(f"  Block at     : {settings.score_threshold_block}")
    print(f"  Cost of miss : Rs {settings.cost_false_negative:,.0f}")
    print(f"  Cost of FP   : Rs {settings.cost_false_positive:,.0f}")
    ratio = settings.cost_false_negative / settings.cost_false_positive
    print(f"  Cost ratio   : {ratio:.1f}x")

    print("\n  --- Directories ---")
    settings.ensure_directories()
    for label, path in [
        ("raw data ", settings.raw_data_path),
        ("processed", settings.processed_data_path),
        ("events   ", settings.event_log_path),
        ("models   ", settings.model_path),
        ("logs     ", settings.log_path),
    ]:
        mark = "OK " if path.exists() else "MISSING"
        print(f"  {mark} {label} : {path}")

    print("\n" + "=" * 62)

    log.info("configuration_check_passed", directories_verified=5)
    log.warning("example_warning", note="this is what a warning looks like")

    print("\n  Configuration loaded and validated successfully.\n")


if __name__ == "__main__":
    main()