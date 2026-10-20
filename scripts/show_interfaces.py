"""Print the signatures the scoring service needs to call."""

import inspect
from pathlib import Path

from streamguard.features import computer as C
from streamguard.features import state as S

print("=" * 72)
print("FeatureComputer")
print("=" * 72)
for name in ("__init__", "compute_features", "update_state", "process"):
    fn = getattr(C.FeatureComputer, name, None)
    if fn:
        print(f"\n  def {name}{inspect.signature(fn)}")
        doc = (fn.__doc__ or "").strip().splitlines()
        if doc:
            print(f"      {doc[0]}")

print()
print("=" * 72)
print("classes in computer.py and state.py")
print("=" * 72)
for mod, label in ((C, "computer"), (S, "state")):
    names = [n for n in dir(mod) if not n.startswith("_") and n[0].isupper()]
    print(f"\n  {label}: {names}")

print()
print("=" * 72)
print("FEATURE_NAMES")
print("=" * 72)
print(f"\n  count: {len(C.FEATURE_NAMES)}")
print(f"  first 5: {C.FEATURE_NAMES[:5]}")
print(f"  last 5:  {C.FEATURE_NAMES[-5:]}")

print()
print("=" * 72)
print("one real event payload")
print("=" * 72)
seg = Path("data/events/transactions/000000.jsonl")
if seg.exists():
    import json
    with seg.open(encoding="utf-8") as fh:
        line = fh.readline()
    ev = json.loads(line)
    print()
    for k, v in ev.items():
        if isinstance(v, dict):
            print(f"  {k}:")
            for kk, vv in v.items():
                print(f"      {kk:<22} {vv!r}")
        else:
            print(f"  {k:<26} {v!r}")
else:
    print(f"\n  {seg} not found")

print()
print("=" * 72)
print("handler.py - how Task 10 wires the computer to the stream")
print("=" * 72)
h = Path("src/streamguard/features/handler.py")
if h.exists():
    print()
    for i, l in enumerate(h.read_text(encoding="utf-8").splitlines()[:60], 1):
        print(f"{i:>4} | {l}")