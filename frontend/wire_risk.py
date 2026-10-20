"""Task 27.3 - styles, api method, and tab wiring."""

from pathlib import Path

# --- 1. api.js ---
api = Path("src/api.js")
t = api.read_text(encoding="utf-8")
if "riskKpis" not in t:
    t = t.rstrip() + """

export function riskKpis({ fnCost, fpCost } = {}) {
  const params = new URLSearchParams()
  if (fnCost) params.set('fn_cost', String(fnCost))
  if (fpCost) params.set('fp_cost', String(fpCost))
  const q = params.toString()
  return request(`/risk-kpis${q ? `?${q}` : ''}`)
}
"""
    api.write_text(t, encoding="utf-8")
print("api riskKpis:", "riskKpis" in api.read_text(encoding="utf-8"))

# --- 2. App.css ---
CSS = r'''

/* Task 27 - risk dashboard */

.risk section { margin-bottom: 1.8rem; }
.risk h3 {
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  color: var(--muted);
  font-weight: 500;
  margin: 0 0 0.8rem;
}

.tiles {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 1px;
  background: var(--line);
  border: 1px solid var(--line);
  border-radius: 8px;
  overflow: hidden;
}

.tile { background: var(--panel); padding: 1rem 1.1rem; }
.tile-label {
  font-size: 0.72rem;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.tile-value { font-size: 1.5rem; font-weight: 600; margin: 0.25rem 0; }
.tile-sub { font-size: 0.75rem; color: var(--muted); }
.tile.ok .tile-value { color: var(--ok); }
.tile.warn .tile-value { color: var(--warn); }
.tile.bad .tile-value { color: var(--bad); }

.charts {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1.2rem;
  margin-bottom: 1.8rem;
}

.chart-card {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 1.2rem;
  margin: 0 !important;
}

@media (max-width: 900px) {
  .charts { grid-template-columns: 1fr; }
}
'''

css = Path("src/App.css")
c = css.read_text(encoding="utf-8")
if ".tiles" not in c:
    css.write_text(c.rstrip() + CSS, encoding="utf-8")
print("css .tiles:", ".tiles" in css.read_text(encoding="utf-8"))

# --- 3. App.jsx ---
app = Path("src/App.jsx")
j = app.read_text(encoding="utf-8")

if "import RiskDashboard" not in j:
    j = j.replace(
        "import CaseQueue from './CaseQueue'",
        "import CaseQueue from './CaseQueue'\nimport RiskDashboard from './RiskDashboard'",
    )

old = """        {tab === 'risk' && (
          <div className="card">
            <h2>Risk dashboard</h2>
            <p className="muted">Arrives in Task 27.</p>
          </div>
        )}"""
new = "        {tab === 'risk' && <RiskDashboard />}"

if old in j:
    j = j.replace(old, new)

app.write_text(j, encoding="utf-8")
print("jsx import:", "import RiskDashboard" in j)
print("jsx uses  :", "<RiskDashboard />" in j)
print("placeholder gone:", "Arrives in Task 27" not in j)