"""Task 27.2 - write src/RiskDashboard.jsx."""

from pathlib import Path

SRC = r'''/**
 * src/RiskDashboard.jsx
 *
 * Task 27 - the risk manager's view: money, mix, and label supply.
 *
 * Requires read_stats, which only risk_manager holds. An analyst
 * reaching this gets a 403 from the server, which the tab bar already
 * avoids by disabling the button.
 */

import { useCallback, useEffect, useState } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  LineChart, Line, Legend, CartesianGrid,
} from 'recharts'
import * as api from './api'

const COLORS = { approve: '#3fb950', review: '#d29922', block: '#f85149' }

function money(n) {
  if (n >= 10000000) return `\u20B9${(n / 10000000).toFixed(2)}Cr`
  if (n >= 100000) return `\u20B9${(n / 100000).toFixed(2)}L`
  return `\u20B9${n.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`
}

function Tile({ label, value, sub, tone }) {
  return (
    <div className={`tile ${tone || ''}`}>
      <div className="tile-label">{label}</div>
      <div className="tile-value">{value}</div>
      {sub && <div className="tile-sub">{sub}</div>}
    </div>
  )
}

export default function RiskDashboard() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    try {
      setData(await api.riskKpis())
      setError(null)
    } catch (err) {
      setError(err.message)
    }
  }, [])

  useEffect(() => {
    load()
    const id = setInterval(load, 10000)
    return () => clearInterval(id)
  }, [load])

  if (error) return <div className="error">{error}</div>
  if (!data) return <div className="empty">Loading...</div>

  const mix = {}
  data.mix.forEach((m) => { mix[m.action] = m })
  const total = data.mix.reduce((s, m) => s + m.n, 0)
  const flagged = (mix.review?.n || 0) + (mix.block?.n || 0)

  // Hourly counts pivoted into one row per hour for the line chart.
  const byHour = {}
  data.hourly.forEach((h) => {
    const key = h.hour.slice(11, 16)
    byHour[key] = byHour[key] || { hour: key, approve: 0, review: 0, block: 0 }
    byHour[key][h.action] = h.n
  })
  const hourly = Object.values(byHour).slice(-24)

  const buckets = data.score_buckets.map((b) => ({
    range: `${((b.bucket - 1) / 10).toFixed(1)}`,
    n: b.n,
  }))

  const labels = data.verdicts.filter(
    (v) => v.verdict === 'confirmed_fraud' || v.verdict === 'legitimate',
  )
  const labelTotal = labels.reduce((s, v) => s + v.n, 0)

  return (
    <div className="risk">
      <section>
        <h3>Money impact</h3>
        <div className="tiles">
          <Tile
            label="Fraud prevented"
            value={money(data.money.fraud_prevented_amount)}
            sub={`${data.money.fraud_prevented_n} confirmed`}
            tone="ok"
          />
          <Tile
            label="False alarm cost"
            value={money(data.money.false_alarm_cost)}
            sub={`${data.money.false_alarms_n} blocked but legitimate`}
            tone="bad"
          />
          <Tile
            label="Net"
            value={money(data.money.net)}
            sub="prevented minus false alarm cost"
            tone={data.money.net >= 0 ? 'ok' : 'bad'}
          />
        </div>
        <p className="muted small">
          Based on <strong>confirmed analyst verdicts only</strong>. A
          blocked transaction nobody reviewed is not counted as prevented
          fraud - claiming it would be marking our own homework.
          Assumptions: a missed fraud costs{' '}
          {money(data.money.fn_cost_assumption)}, a blocked customer{' '}
          {money(data.money.fp_cost_assumption)}.
        </p>
      </section>

      <section>
        <h3>Decision mix</h3>
        <div className="tiles">
          <Tile label="Scored" value={total.toLocaleString()} />
          <Tile
            label="Approved"
            value={(mix.approve?.n || 0).toLocaleString()}
            tone="ok"
          />
          <Tile
            label="Review"
            value={(mix.review?.n || 0).toLocaleString()}
            tone="warn"
          />
          <Tile
            label="Blocked"
            value={(mix.block?.n || 0).toLocaleString()}
            tone="bad"
          />
          <Tile
            label="Flagged"
            value={total ? `${((100 * flagged) / total).toFixed(2)}%` : '-'}
            sub="of all traffic"
          />
        </div>
      </section>

      <div className="charts">
        <section className="chart-card">
          <h3>Decisions per hour</h3>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={hourly}>
              <CartesianGrid stroke="#242c38" strokeDasharray="3 3" />
              <XAxis dataKey="hour" stroke="#8b98a8" fontSize={11} />
              <YAxis stroke="#8b98a8" fontSize={11} />
              <Tooltip
                contentStyle={{
                  background: '#171d26',
                  border: '1px solid #242c38',
                  borderRadius: 6,
                }}
              />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Line type="monotone" dataKey="approve" stroke={COLORS.approve} dot={false} />
              <Line type="monotone" dataKey="review" stroke={COLORS.review} dot={false} />
              <Line type="monotone" dataKey="block" stroke={COLORS.block} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </section>

        <section className="chart-card">
          <h3>Score distribution</h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={buckets}>
              <CartesianGrid stroke="#242c38" strokeDasharray="3 3" />
              <XAxis dataKey="range" stroke="#8b98a8" fontSize={11} />
              <YAxis stroke="#8b98a8" fontSize={11} scale="log" domain={[1, 'auto']} />
              <Tooltip
                contentStyle={{
                  background: '#171d26',
                  border: '1px solid #242c38',
                  borderRadius: 6,
                }}
              />
              <Bar dataKey="n" fill="#4a9eff" />
            </BarChart>
          </ResponsiveContainer>
          <p className="muted small">
            Log scale. Almost everything sits in the lowest bucket - at this
            prevalence that is the expected shape, and a linear axis would
            show one bar and nine empty slots.
          </p>
        </section>
      </div>

      <section>
        <h3>Model monitoring</h3>
        <div className="tiles">
          <Tile label="p50 latency" value={`${data.latency.p50_ms.toFixed(1)} ms`} />
          <Tile label="p95" value={`${data.latency.p95_ms.toFixed(1)} ms`} />
          <Tile label="p99" value={`${data.latency.p99_ms.toFixed(1)} ms`} />
          <Tile label="max" value={`${data.latency.max_ms.toFixed(1)} ms`} />
        </div>
        <table className="kv">
          <tbody>
            {data.models.map((m) => (
              <tr key={m.version}>
                <th>{m.version}</th>
                <td>
                  {m.n.toLocaleString()} decisions
                  <span className="muted small">
                    {' '}
                    &middot; {m.first?.slice(0, 16).replace('T', ' ')} to{' '}
                    {m.last?.slice(0, 16).replace('T', ' ')}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section>
        <h3>Label supply for retraining</h3>
        <div className="tiles">
          {data.verdicts.map((v) => (
            <Tile
              key={v.verdict}
              label={v.verdict.replace('_', ' ')}
              value={v.n.toLocaleString()}
              tone={
                v.verdict === 'confirmed_fraud'
                  ? 'bad'
                  : v.verdict === 'legitimate'
                  ? 'ok'
                  : ''
              }
            />
          ))}
        </div>
        <p className="muted small">
          <strong>{labelTotal}</strong> usable labels. Only confirmed_fraud
          and legitimate feed retraining - inconclusive and pending do not.
          Queue: {JSON.stringify(data.queue)}
        </p>
      </section>
    </div>
  )
}
'''

p = Path("src/RiskDashboard.jsx")
p.write_text(SRC, encoding="utf-8")
print("src/RiskDashboard.jsx", p.stat().st_size, "bytes")
print("ends correctly:", SRC.rstrip().endswith("}"))