"""Print the _card_not_present method as it currently stands."""

from pathlib import Path

p = Path("src/streamguard/generator/fraud_injector.py")
lines = p.read_text(encoding="utf-8").splitlines()

start = None
for i, line in enumerate(lines):
    if "def _card_not_present" in line:
        start = i
        break

if start is None:
    print("method not found")
else:
    for j in range(start, min(start + 55, len(lines))):
        print(f"{j + 1:>4} | {lines[j]}")