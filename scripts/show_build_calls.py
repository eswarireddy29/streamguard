"""Print every _build() call site in fraud_injector.py with context."""

from pathlib import Path

p = Path("src/streamguard/generator/fraud_injector.py")
lines = p.read_text(encoding="utf-8").splitlines()

for i, line in enumerate(lines):
    if "self._build(" in line:
        print("=" * 60)
        print(f"line {i + 1}")
        print("=" * 60)
        for j in range(i, min(i + 14, len(lines))):
            print(f"{j + 1:>4} | {lines[j]}")
        print()