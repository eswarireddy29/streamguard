import { useEffect, useState } from 'react'
import * as api from './api'
import LiveStream from './LiveStream'
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
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
        </label>
        <label>
          Password
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
        </label>
        <button type="submit" disabled={busy || !password}>
          {busy ? 'Signing in...' : 'Sign in'}
        </button>
        {error && <div className="error">{error}</div>}
        <div className="hint">
          Development users: <code>analyst</code> / <code>manager</code> / <code>payment-switch</code>
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
        if (alive) { setHealth(h); setError(null) }
      } catch (err) {
        if (alive) setError(err.message)
      }
    }
    poll()
    const id = setInterval(poll, 15000)
    return () => { alive = false; clearInterval(id) }
  }, [])

  if (error) return <div className="healthbar down">* {error}</div>
  if (!health) return <div className="healthbar">* checking...</div>

  return (
    <div className="healthbar up">
      * {health.status} &middot; {health.model_version} &middot; {health.n_features} features
      &middot; {health.cards_in_state.toLocaleString()} cards
      &middot; {health.scored.toLocaleString()} scored
    </div>
  )
}

export default function App() {
  const [signedIn, setSignedIn] = useState(Boolean(api.getToken()))
  const [me, setMe] = useState(null)
  const [tab, setTab] = useState('stream')
  useEffect(() => {
    if (!signedIn) return
    api.whoami().then(setMe).catch(() => setSignedIn(false))
  }, [signedIn])

  if (!signedIn) return <Login onSignedIn={() => setSignedIn(true)} />

  return (
    <div className="app">
      <header>
        <div className="brand">
          <strong>StreamGuard</strong>
          <span className="muted"> fraud console</span>
        </div>
        <div className="session">
          <span className="role">{me?.role ?? '...'}</span>
          <span className="muted">{me?.username}</span>
          <button className="link" onClick={() => { api.clearSession(); setSignedIn(false); setMe(null) }}>
            Sign out
          </button>
        </div>
      </header>

      <HealthBar />

          <nav className="tabs">
        <button
          className={tab === 'stream' ? 'active' : ''}
          onClick={() => setTab('stream')}
          disabled={!api.can('read_cases')}
        >
          Live stream
        </button>
        <button
          className={tab === 'cases' ? 'active' : ''}
          onClick={() => setTab('cases')}
          disabled={!api.can('read_cases')}
        >
          Case queue
        </button>
        <button
          className={tab === 'risk' ? 'active' : ''}
          onClick={() => setTab('risk')}
          disabled={!api.can('read_stats')}
        >
          Risk dashboard
        </button>
      </nav>

      <main>
        {tab === 'stream' && <LiveStream />}
        {tab === 'cases' && (
          <div className="card">
            <h2>Case queue</h2>
            <p className="muted">Arrives in Task 26.</p>
          </div>
        )}
        {tab === 'risk' && (
          <div className="card">
            <h2>Risk dashboard</h2>
            <p className="muted">Arrives in Task 27.</p>
          </div>
        )}
      </main>
    </div>
  )
}
