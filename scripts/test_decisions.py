"""
scripts/test_decisions.py

Task 21 - does the decision engine do what it claims?

Each case checks one rule in isolation, with the expected outcome
stated up front. A rule that has never been exercised cannot be
trusted - the same argument as the Task 11 test suite.

    python scripts/test_decisions.py
"""

from __future__ import annotations

import typer

from streamguard.api.decisions import (
    DecisionEngine, DecisionConfig, Decision,
)
from streamguard.utils.logging_config import setup_logging

app = typer.Typer(add_completion=False)
LINE = "=" * 72


def payload(card="CARD0000001", merchant="MERCH000001",
            device="DEV0000001", amount=1000.0) -> dict:
    return {"card_ref": card, "merchant_ref": merchant,
            "device_ref": device, "amount": amount}


@app.command()
def main() -> None:
    setup_logging()
    print(LINE)
    print("TASK 21 - DECISION ENGINE")
    print(LINE)

    engine = DecisionEngine(DecisionConfig())
    engine.block_card("CARD_STOLEN")
    engine.trust_card("CARD_TRUSTED")
    engine.watch_merchant("MERCH_WATCHED")

    cases = [
        ("low score, nothing special",
         payload(), 0.001, Decision.APPROVE, "model"),

        ("score above review threshold",
         payload(), 0.02, Decision.REVIEW, "model"),

        ("score above block threshold",
         payload(), 0.50, Decision.BLOCK, "model"),

        ("STOLEN CARD, score near zero",
         payload(card="CARD_STOLEN"), 0.0001, Decision.BLOCK, "rule"),

        ("watched merchant, low score",
         payload(merchant="MERCH_WATCHED"), 0.001, Decision.REVIEW, "rule"),

        ("high value, low score",
         payload(amount=250_000), 0.001, Decision.REVIEW, "rule"),

        ("very high value, low score",
         payload(amount=1_500_000), 0.001, Decision.BLOCK, "rule"),

        ("trusted card, mid score",
         payload(card="CARD_TRUSTED"), 0.02, Decision.APPROVE, "rule"),

        ("trusted card CANNOT bypass a block score",
         payload(card="CARD_TRUSTED"), 0.90, Decision.BLOCK, "model"),

        ("trusted card CANNOT bypass a high value",
         payload(card="CARD_TRUSTED", amount=250_000), 0.001,
         Decision.REVIEW, "rule"),
    ]

    print()
    print(f"  {'case':<46}{'expect':>9}{'got':>9}{'src':>8}")
    print("  " + "-" * 72)

    failures = 0
    for name, p, prob, expected, expected_src in cases:
        r = engine.decide(p, prob)
        ok = r.decision == expected and r.source == expected_src
        if not ok:
            failures += 1
        mark = "" if ok else "   <-- FAIL"
        print(f"  {name:<46}{expected.value:>9}"
              f"{r.decision.value:>9}{r.source:>8}{mark}")

    print()
    print(LINE)
    print("EXPLANATIONS (what an analyst reads)")
    print(LINE)
    print()
    for name, p, prob, _, _ in cases[3:8]:
        r = engine.decide(p, prob)
        print(f"  {name}:")
        print(f"      {r.explain()}")
        print()

    print(LINE)
    print("ENGINE STATS")
    print(LINE)
    s = engine.stats()
    print()
    print(f"  decisions      {s['decisions']}")
    print(f"  overrides      {s['overrides']} of {s['total']} "
          f"({s['override_rate'] * 100:.0f}%)")
    print(f"  rules fired    {s['rules_fired']}")
    print(f"  lists          {s['lists']}")

    print()
    print(LINE)
    if failures:
        print(f"  {failures} CASE(S) FAILED")
        raise typer.Exit(1)
    print(f"  all {len(cases)} cases passed")
    print(LINE)


if __name__ == "__main__":
    app()