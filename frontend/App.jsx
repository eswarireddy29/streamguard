import { useEffect, useState } from 'react'
import * as api from './api'
import './App.css'

function Login({ onSignedIn }) {
  const [username, setUsername] = useState('analyst')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  async function submit(e) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await api.login(username, password)
      onSignedIn()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login-wrap">
      <form className="card login" onSubmit={submit}>
        <h1>StreamGuard</h1>
        <p className="muted">Fraud detection console</p>

        <label>
          Username
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
          />
        </label>

        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
          />
        </label>

        <button type="submit" disabled={busy || !password}>
          {busy ? 'Signing in…' : 'Sign in'}
        </button>

        {error && <div className="error">{error}</div>}

        <div className="hint">
          Development users: <code>analyst</code> / <code>manager</code> /{' '}
          <code>payment-switch</code>
        </div>
      </form>
    </div>
  )
}

function HealthBar() {
  const [health, setHealth] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let alive = true
    async function poll() {
      try {
        const h = await api.health()
        if (alive) {
          setHealth(h)
          setError(null)
        }
      } catch (err) {
        if (alive) setError(err.message)
      }
    }
    poll()
    const id = setInterval(poll, 15000)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [])

  if (error) return <div className="healthbar down">● {error}</div>
  if (!health) return <div className="healthbar">● checking…</div>

  return (
    <div className="healthbar up">
      ● {health.status} · {health.model_version} · {health.n_features} features ·{' '}
      {health.cards_in_state.toLocaleString()} cards ·{' '}
      {health.scored.toLocaleString()} scored
    </div>
  )
}

export default function App() {
  const [signedIn, setSignedIn] = useState(Boolean(api.getToken()))
  const [me, setMe] = useState(null)

  useEffect(() => {
    if (!signedIn) return
    api
      .whoami()
      .then(setMe)
      .catch(() => {
        setSignedIn(false)
      })
  }, [signedIn])

  if (!signedIn) {
    return <Login onSignedIn={() => setSignedIn(true)} />
  }

  return (
    <div className="app">
      <header>
        <div className="brand">
          <strong>StreamGuard</strong>
          <span className="muted"> fraud console</span>
        </div>
        <div className="session">
          <span className="role">{me?.role ?? '…'}</span>
          <span className="muted">{me?.username}</span>
          <button
            className="link"
            onClick={() => {
              api.clearSession()
              setSignedIn(false)
              setMe(null)
            }}
          >
            Sign out
          </button>
        </div>
      </header>

      <HealthBar />

      <main>
        <div className="card">
          <h2>Signed in</h2>
          <p className="muted">
            The shell, API client and session are working. Pages arrive in
            Tasks 25–27.
          </p>
          <table className="kv">
            <tbody>
              <tr>
                <th>User</th>
                <td>{me?.username}</td>
              </tr>
              <tr>
                <th>Role</th>
                <td>{me?.role}</td>
              </tr>
              <tr>
                <th>Permissions</th>
                <td>{(me?.permissions ?? []).join(', ')}</td>
              </tr>
              <tr>
                <th>Token expires</th>
                <td>{me?.expires_at?.slice(0, 19).replace('T', ' ')}</td>
              </tr>
            </tbody>
          </table>

          <div className="nav-preview">
            <span className={api.can('read_cases') ? '' : 'disabled'}>
              Live stream (Task 25)
            </span>
            <span className={api.can('read_cases') ? '' : 'disabled'}>
              Case queue (Task 26)
            </span>
            <span className={api.can('read_stats') ? '' : 'disabled'}>
              Risk dashboard (Task 27)
            </span>
          </div>
          <p className="muted small">
            Greyed items are hidden for this role. The server enforces this
            with 403 — the UI only avoids showing a button that would fail.
          </p>
        </div>
      </main>
    </div>
  )
}