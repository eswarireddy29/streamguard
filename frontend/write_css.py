"""One-off: write src/App.css, bypassing the editor."""

from pathlib import Path

CSS = r''':root {
  --bg: #0f1419;
  --panel: #171d26;
  --line: #242c38;
  --text: #e6edf3;
  --muted: #8b98a8;
  --accent: #4a9eff;
  --ok: #3fb950;
  --warn: #d29922;
  --bad: #f85149;
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
}

.muted { color: var(--muted); }
.small { font-size: 0.85rem; }

.app { max-width: 1200px; margin: 0 auto; padding: 0 1.5rem 3rem; }

header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1.25rem 0;
  border-bottom: 1px solid var(--line);
}

.brand strong { font-size: 1.1rem; letter-spacing: 0.02em; }

.session { display: flex; align-items: center; gap: 0.9rem; font-size: 0.9rem; }

.role {
  background: var(--line);
  padding: 0.2rem 0.6rem;
  border-radius: 999px;
  font-size: 0.78rem;
  letter-spacing: 0.03em;
}

.healthbar {
  font-size: 0.82rem;
  color: var(--muted);
  padding: 0.6rem 0;
  border-bottom: 1px solid var(--line);
}
.healthbar.up { color: var(--ok); }
.healthbar.down { color: var(--bad); }

main { padding-top: 1.5rem; }

.card {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 1.5rem;
}

.card h2 { margin: 0 0 0.4rem; font-size: 1rem; }

.kv { margin-top: 1.2rem; border-collapse: collapse; font-size: 0.9rem; }
.kv th {
  text-align: left;
  color: var(--muted);
  font-weight: 400;
  padding: 0.35rem 1.5rem 0.35rem 0;
  vertical-align: top;
}
.kv td { padding: 0.35rem 0; }

.nav-preview {
  display: flex;
  gap: 1.5rem;
  margin-top: 1.5rem;
  padding-top: 1.2rem;
  border-top: 1px solid var(--line);
  font-size: 0.9rem;
}
.nav-preview .disabled { color: var(--muted); opacity: 0.4; }

.login-wrap {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 1.5rem;
}

.login { width: 100%; max-width: 360px; }
.login h1 { margin: 0; font-size: 1.3rem; }
.login p { margin: 0.3rem 0 1.5rem; font-size: 0.9rem; }

.login label {
  display: block;
  margin-bottom: 1rem;
  font-size: 0.82rem;
  color: var(--muted);
}

.login input {
  display: block;
  width: 100%;
  margin-top: 0.35rem;
  padding: 0.6rem 0.7rem;
  background: var(--bg);
  border: 1px solid var(--line);
  border-radius: 6px;
  color: var(--text);
  font-size: 0.95rem;
}
.login input:focus { outline: none; border-color: var(--accent); }

.login button {
  width: 100%;
  padding: 0.65rem;
  background: var(--accent);
  color: #06121f;
  border: none;
  border-radius: 6px;
  font-size: 0.95rem;
  font-weight: 600;
  cursor: pointer;
}
.login button:disabled { opacity: 0.4; cursor: not-allowed; }

button.link {
  background: none;
  border: none;
  color: var(--accent);
  cursor: pointer;
  font-size: 0.9rem;
  padding: 0;
}

.error {
  margin-top: 1rem;
  padding: 0.6rem 0.75rem;
  background: rgba(248, 81, 73, 0.1);
  border: 1px solid rgba(248, 81, 73, 0.3);
  border-radius: 6px;
  color: var(--bad);
  font-size: 0.85rem;
}

.hint {
  margin-top: 1.25rem;
  font-size: 0.78rem;
  color: var(--muted);
  line-height: 1.6;
}
.hint code {
  background: var(--bg);
  padding: 0.1rem 0.3rem;
  border-radius: 3px;
}
'''

p = Path("src/App.css")
p.write_text(CSS, encoding="utf-8")
print("src/App.css", p.stat().st_size, "bytes")
print("has :root", ":root" in CSS)
print("has .login-wrap", ".login-wrap" in CSS)