/**
 * src/LiveStream.jsx
 *
 * Task 25 - decisions as they happen.
 *
 * Polls rather than using a websocket: a dropped poll is
 * self-healing, where a dropped socket needs reconnection logic. For
 * a console watched by a handful of analysts, that complexity is not
 * worth buying.
 *
 * Only rows newer than the highest id already held are requested, so
 * the payload does not grow with the table.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import * as api from './api'

const MAX_ROWS = 120
const POLL_MS = 2000

function money(n) {
  return `₹${n.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`
}

function Stat({ label, value, tone }) {
  return (
    <div className={`stat ${tone || ''}`}>
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
    </div>
  )
}

export default function LiveStream() {
  const [rows, setRows] = useState([])
  const [totals, setTotals] = useState({})
  const [error, setError] = useState(null)
  const [live, setLive] = useState(true)
  const maxId = useRef(0)

  const poll = useCallback(async () => {
    try {
      const data = await api.recentDecisions({
        limit: 60,
        sinceId: maxId.current,
      })
      setError(null)
      setTotals(data.totals || {})

      if (data.decisions?.length) {
        maxId.current = Math.max(maxId.current, data.max_id)
        setRows((prev) => [...data.decisions, ...prev].slice(0, MAX_ROWS))
      }
    } catch (err) {
      setError(err.message)
    }
  }, [])

  useEffect(() => {
    poll()
    if (!live) return
    const id = setInterval(poll, POLL_MS)
    return () => clearInterval(id)
  }, [poll, live])

  const approve = totals.approve?.n ?? 0
  const review = totals.review?.n ?? 0
  const block = totals.block?.n ?? 0
  const total = approve + review + block
  const flagged = review + block
  const meanLatency =
    total > 0
      ? (
          ((totals.approve?.mean_latency_ms ?? 0) * approve +
            (totals.review?.mean_latency_ms ?? 0) * review +
            (totals.block?.mean_latency_ms ?? 0) * block) /
          total
        ).toFixed(1)
      : '—'

  return (
    <div className="stream">
      <div className="stream-head">
        <h2>Live decisions</h2>
        <button className="link" onClick={() => setLive((v) => !v)}>
          {live ? '⏸ Pause' : '▶ Resume'}
        </button>
      </div>

      <div className="stats">
        <Stat label="scored" value={total.toLocaleString()} />
        <Stat label="approved" value={approve.toLocaleString()} tone="ok" />
        <Stat label="review" value={review.toLocaleString()} tone="warn" />
        <Stat label="blocked" value={block.toLocaleString()} tone="bad" />
        <Stat
          label="flagged"
          value={total ? `${((100 * flagged) / total).toFixed(2)}%` : '—'}
        />
        <Stat label="mean latency" value={`${meanLatency} ms`} />
      </div>

      {error && <div className="error">{error}</div>}

      {rows.length === 0 && !error && (
        <div className="empty">
          Nothing scored yet. Start the feeder:
          <br />
          <code>python scripts/replay_stream.py</code>
        </div>
      )}

      {rows.length > 0 && (
        <table className="stream-table">
          <thead>
            <tr>
              <th>decision</th>
              <th>score</th>
              <th>transaction</th>
              <th>amount</th>
              <th>where</th>
              <th>channel</th>
              <th>ms</th>
              <th>case</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className={`row-${r.action}`}>
                <td>
                  <span className={`pill ${r.action}`}>{r.action}</span>
                </td>
                <td className="num">{r.score.toFixed(4)}</td>
                <td className="mono">{r.transaction_ref}</td>
                <td className="num">{money(r.amount)}</td>
                <td>
                  {r.city}
                  <span className="muted"> {r.country}</span>
                </td>
                <td className="muted small">
                  {r.channel} / {r.entry_mode}
                </td>
                <td className="num muted">{r.latency_ms.toFixed(1)}</td>
                <td className="mono small">{r.case_ref || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}