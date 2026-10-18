"""
Generate and load transaction activity, with fraud injected.

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
from streamguard.generator.fraud_injector import FraudInjector  # noqa: E402
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

    # --- Fraud episodes, generated up front and bucketed by day ---
    estimated_normal = int(
        sum(c.txns_per_day for c in population.customers) * n_days
    )
    target_fraud = int(estimated_normal * settings.fraud_rate)

    print(f"  Estimated normal transactions : {estimated_normal:,}")
    print(f"  Target fraud transactions     : {target_fraud:,} "
          f"({settings.fraud_rate:.2%})\n")

    injector = FraudInjector(population, seed=random_seed, start=generator.start)
    episodes = injector.generate_episodes(target_fraud, n_days)

    fraud_by_day: dict[int, list] = {}
    for episode in episodes:
        for txn in episode.transactions:
            day_index = (txn.occurred_at - generator.start).days
            if 0 <= day_index < n_days:
                fraud_by_day.setdefault(day_index, []).append(txn)

    fraud_total = sum(len(v) for v in fraud_by_day.values())
    print(f"  Fraud episodes : {len(episodes):,}")
    print(f"  Fraud rows     : {fraud_total:,}\n")

    # --- Generate day by day, merging fraud into each day ---
    print(f"  Generating {n_days} days...\n")
    total = 0
    fraud_written = 0

    for day, transactions in generator.stream_days(n_days):
        day_fraud = fraud_by_day.get(day, [])
        if day_fraud:
            # Re-sort: the feature engine replays history in order
            transactions = sorted(
                transactions + day_fraud, key=lambda t: t.occurred_at
            )
            fraud_written += len(day_fraud)

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
    print(f"  Fraud rows   : {fraud_written:,} "
          f"({fraud_written / max(total, 1):.3%})")
    print(f"  Skipped      : {loader.skipped:,}")
    print(f"  Time         : {elapsed:.1f}s")
    print(f"  Rate         : {total / elapsed:,.0f}/s")
    print(f"  Per day avg  : {total / n_days:,.0f}")
    print("=" * 62 + "\n")

    if loader.skipped:
        print(f"  WARNING: {loader.skipped:,} transactions skipped — "
              f"investigate before continuing.\n")

    log.info("transaction_generation_complete",
             total=total, fraud=fraud_written, skipped=loader.skipped,
             seconds=round(elapsed, 1))


if __name__ == "__main__":
    app()