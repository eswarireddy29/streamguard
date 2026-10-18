"""
Generate and load normal transaction activity.

    python scripts/generate_transactions.py
    python scripts/generate_transactions.py --days 7
    python scripts/generate_transactions.py --days 90 --no-truncate
"""

import sys
import time
from pathlib import Path

import typer

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from streamguard.config.settings import settings  # noqa: E402
from streamguard.generator.entities import PopulationGenerator  # noqa: E402
from streamguard.generator.transactions import TransactionGenerator  # noqa: E402
from streamguard.generator.txn_loader import TransactionLoader  # noqa: E402
from streamguard.utils.logging_config import get_logger, setup_logging  # noqa: E402

app = typer.Typer(add_completion=False)


@app.command()
def main(
    days: int = typer.Option(None, help="Days to simulate"),
    seed: int = typer.Option(None, help="Random seed"),
    truncate: bool = typer.Option(True, help="Clear existing transactions first"),
) -> None:
    setup_logging()
    log = get_logger(__name__)

    n_days = days or settings.simulation_days
    random_seed = seed if seed is not None else settings.random_seed

    print("\n" + "=" * 62)
    print("  STREAMGUARD — TRANSACTION GENERATION")
    print("=" * 62)
    print(f"\n  Days     : {n_days}")
    print(f"  Seed     : {random_seed}")
    print(f"  Truncate : {truncate}\n")

    started = time.perf_counter()

    # Rebuild the SAME population in memory. The database holds the
    # persisted entities, but the generator needs the behaviour knobs
    # (night_owl, category_affinity, travel_propensity) that are
    # deliberately never stored. Same seed = same population.
    print("  Rebuilding population in memory (same seed)...")
    population = PopulationGenerator(seed=random_seed).generate_population(
        settings.n_customers, settings.n_merchants
    )

    if truncate:
        TransactionLoader.truncate_transactions()

    generator = TransactionGenerator(population, seed=random_seed)
    loader = TransactionLoader()

    print(f"\n  Generating {n_days} days...\n")
    total = 0

    for day, transactions in generator.stream_days(n_days):
        written = loader.insert_batch(transactions)
        total += written

        if (day + 1) % 10 == 0 or day == 0 or day == n_days - 1:
            elapsed = time.perf_counter() - started
            rate = total / elapsed if elapsed > 0 else 0
            print(f"  day {day + 1:>3}/{n_days}  "
                  f"+{written:>6,}  total {total:>9,}  "
                  f"{rate:>7,.0f}/s")

    loader.analyze()
    elapsed = time.perf_counter() - started

    print("\n  --- Complete ---")
    print(f"  Transactions : {total:,}")
    print(f"  Skipped      : {loader.skipped:,}")
    print(f"  Time         : {elapsed:.1f}s")
    print(f"  Rate         : {total / elapsed:,.0f}/s")
    print(f"  Per day avg  : {total / n_days:,.0f}")
    print("=" * 62 + "\n")

    if loader.skipped:
        print(f"  WARNING: {loader.skipped:,} transactions skipped — "
              f"investigate before continuing.\n")

    log.info("transaction_generation_complete",
             total=total, skipped=loader.skipped, seconds=round(elapsed, 1))


if __name__ == "__main__":
    app()