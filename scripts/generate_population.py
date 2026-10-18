"""
Generate and load the synthetic population.

    python scripts/generate_population.py
    python scripts/generate_population.py --customers 1000 --merchants 200
    python scripts/generate_population.py --seed 7 --no-truncate
"""

import sys
import time
from pathlib import Path

import typer

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from streamguard.config.settings import settings  # noqa: E402
from streamguard.generator.entities import PopulationGenerator  # noqa: E402
from streamguard.generator.loader import ReferenceLoader  # noqa: E402
from streamguard.utils.logging_config import get_logger, setup_logging  # noqa: E402

app = typer.Typer(add_completion=False)


@app.command()
def main(
    customers: int = typer.Option(None, help="Number of customers"),
    merchants: int = typer.Option(None, help="Number of merchants"),
    seed: int = typer.Option(None, help="Random seed"),
    truncate: bool = typer.Option(True, help="Clear existing data first"),
) -> None:
    setup_logging()
    log = get_logger(__name__)

    n_customers = customers or settings.n_customers
    n_merchants = merchants or settings.n_merchants
    random_seed = seed if seed is not None else settings.random_seed

    print("\n" + "=" * 62)
    print("  STREAMGUARD — POPULATION GENERATION")
    print("=" * 62)
    print(f"\n  Customers : {n_customers:,}")
    print(f"  Merchants : {n_merchants:,}")
    print(f"  Seed      : {random_seed}")
    print(f"  Truncate  : {truncate}\n")

    started = time.perf_counter()

    generator = PopulationGenerator(seed=random_seed)
    population = generator.generate_population(n_customers, n_merchants)

    generated_at = time.perf_counter()
    print(f"\n  Generated in {generated_at - started:.2f}s")

    loader = ReferenceLoader()
    counts = loader.load(population, truncate=truncate)

    elapsed = time.perf_counter() - started

    print("\n  --- Loaded ---")
    for label, count in counts.items():
        print(f"  {label:<12}: {count:,}")

    print(f"\n  Total time: {elapsed:.2f}s")
    print("=" * 62 + "\n")

    log.info("population_pipeline_complete", seconds=round(elapsed, 2), **counts)


if __name__ == "__main__":
    app()