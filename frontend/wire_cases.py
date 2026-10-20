"""Task 26.3 - wire CaseQueue into the tab shell."""

from pathlib import Path

p = Path("src/App.jsx")
t = p.read_text(encoding="utf-8")

# 1. add the import
if "import CaseQueue" not in t:
    t = t.replace(
        "import LiveStream from './LiveStream'",
        "import LiveStream from './LiveStream'\nimport CaseQueue from './CaseQueue'",
    )

# 2. replace the placeholder block with the real component
old = """        {tab === 'cases' && (
          <div className="card">
            <h2>Case queue</h2>
            <p className="muted">Arrives in Task 26.</p>
          </div>
        )}"""
new = "        {tab === 'cases' && <CaseQueue />}"

if old in t:
    t = t.replace(old, new)
    replaced = True
else:
    replaced = "<CaseQueue />" in t

p.write_text(t, encoding="utf-8")

print("import CaseQueue:", "import CaseQueue" in t)
print("uses CaseQueue  :", "<CaseQueue />" in t)
print("placeholder gone:", "Arrives in Task 26" not in t)
if not replaced:
    print()
    print("  WARNING: the placeholder block was not found.")
    print("  Paste the lines around 'tab === cases' from App.jsx.")