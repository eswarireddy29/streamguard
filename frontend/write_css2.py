"""Task 26.2 - append case-queue styles to src/App.css."""

from pathlib import Path

CSS = r'''

/* Task 26 - case queue */

.cases {
  display: grid;
  grid-template-columns: 340px 1fr;
  gap: 1.2rem;
  align-items: start;
}

.queue-pane, .detail-pane {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 1.2rem;
}

.queue-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.queue-head h2 { margin: 0; font-size: 1rem; }

.queue-head select {
  background: var(--bg);
  border: 1px solid var(--line);
  color: var(--text);
  border-radius: 6px;
  padding: 0.3rem 0.5rem;
  font-size: 0.82rem;
}

.queue-note { margin: 0.6rem 0 1rem; line-height: 1.5; }

.queue { list-style: none; margin: 0; padding: 0; }

.queue li {
  padding: 0.7rem 0.75rem;
  border: 1px solid transparent;
  border-radius: 8px;
  cursor: pointer;
  margin-bottom: 0.3rem;
}
.queue li:hover { background: var(--bg); }
.queue li.selected { background: var(--bg); border-color: var(--accent); }

.queue-top {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.3rem;
}
.queue-bottom {
  display: flex;
  align-items: baseline;
  gap: 0.7rem;
  font-size: 0.82rem;
}
.queue-bottom .score { font-variant-numeric: tabular-nums; }

.pri {
  font-size: 0.68rem;
  font-weight: 700;
  padding: 0.1rem 0.35rem;
  border-radius: 4px;
  background: var(--line);
}
.pri-1 { background: rgba(248, 81, 73, 0.25); color: var(--bad); }
.pri-2 { background: rgba(210, 153, 34, 0.25); color: var(--warn); }

.detail-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}
.detail-head h2 { margin: 0 0 0.2rem; font-size: 1.05rem; }

.detail-stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1rem;
  margin: 1.3rem 0;
  padding: 1rem 0;
  border-top: 1px solid var(--line);
  border-bottom: 1px solid var(--line);
}
.detail-stats .stat-value { font-size: 1.25rem; font-weight: 600; }
.detail-stats .small-val { font-size: 0.95rem; }

.detail section { margin-bottom: 1.6rem; }
.detail h3 {
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  color: var(--muted);
  font-weight: 500;
  margin: 0 0 0.7rem;
}

.shap { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
.shap td { padding: 0.3rem 0.5rem 0.3rem 0; vertical-align: middle; }
.shap-bar-cell { width: 40%; }
.shap-bar {
  height: 6px;
  background: var(--bad);
  border-radius: 3px;
  min-width: 2px;
}
.shap-val { color: var(--bad); font-variant-numeric: tabular-nums; }

.rules { list-style: none; margin: 0; padding: 0; }
.rules li {
  padding: 0.5rem 0;
  border-bottom: 1px solid var(--line);
  font-size: 0.85rem;
}

.btn {
  background: var(--line);
  border: 1px solid var(--line);
  color: var(--text);
  padding: 0.45rem 0.9rem;
  border-radius: 6px;
  font-size: 0.85rem;
  cursor: pointer;
}
.btn:hover { border-color: var(--accent); }
.btn:disabled { opacity: 0.4; cursor: not-allowed; }

.verdict-row { display: flex; gap: 0.5rem; margin: 0.7rem 0; flex-wrap: wrap; }
.btn.verdict.bad { border-color: rgba(248, 81, 73, 0.4); color: var(--bad); }
.btn.verdict.ok { border-color: rgba(63, 185, 80, 0.4); color: var(--ok); }

.detail textarea {
  width: 100%;
  margin-top: 0.7rem;
  background: var(--bg);
  border: 1px solid var(--line);
  border-radius: 6px;
  color: var(--text);
  padding: 0.6rem;
  font-size: 0.85rem;
  font-family: inherit;
  resize: vertical;
}
.detail textarea:focus { outline: none; border-color: var(--accent); }

.closed-note {
  padding: 0.8rem;
  background: var(--bg);
  border-radius: 6px;
  font-size: 0.88rem;
}

.audit { list-style: none; margin: 0; padding: 0; font-size: 0.83rem; }
.audit li { padding: 0.3rem 0; }

@media (max-width: 900px) {
  .cases { grid-template-columns: 1fr; }
}
'''

p = Path("src/App.css")
p.write_text(p.read_text(encoding="utf-8").rstrip() + CSS, encoding="utf-8")
print("src/App.css", p.stat().st_size, "bytes")
print("has .cases:", ".cases" in p.read_text(encoding="utf-8"))