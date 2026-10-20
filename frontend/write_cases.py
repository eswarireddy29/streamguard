"""Task 26.1 - write src/CaseQueue.jsx."""

from pathlib import Path

SRC = r'''/**
 * src/CaseQueue.jsx
 *
 * Task 26 - the analyst's working view.
 *
 * Two panes: the queue on the left, the selected case on the right.
 * A list-then-detail layout rather than separate pages, because an
 * analyst works through a queue and should not lose their place on
 * every verdict.
 *
 * The verdict submitted here is the label Task 30 retrains on, which
 * is why the UI states that plainly rather than treating it as a
 * status dropdown.
 */

import { useCallback, useEffect, useState } from 'react'
import * as api from './api'

const VERDICTS = [
  {
    value: 'confirmed_fraud',
    label: 'Confirmed fraud',
    tone: 'bad',
    note: 'Used as a positive training label',
  },
  {
    value: 'legitimate',
    label: 'Legitimate',
    tone: 'ok',
    note: 'Used as a negative training label',
  },
  {
    value: 'inconclusive',
    label: 'Inconclusive',
    tone: 'muted',
    note: 'Recorded but NOT used for training',
  },
]

function money(n) {
  return `\u20B9${n.toLocaleString('en-IN', { maximumFractionDigits: 2 })}`
}

function when(iso) {
  return iso ? iso.slice(0, 19).replace('T', ' ') : '\u2014'
}

function Queue({ cases, selected, onSelect, loading }) {
  if (loading && cases.length === 0) {
    return <div className="empty">Loading the queue...</div>
  }
  if (cases.length === 0) {
    return (
      <div className="empty">
        No open cases.
        <br />
        Run the feeder to generate some:
        <br />
        <code>python scripts/replay_stream.py</code>
      </div>
    )
  }

  return (
    <ul className="queue">
      {cases.map((c) => (
        <li
          key={c.case_ref}
          className={c.case_ref === selected ? 'selected' : ''}
          onClick={() => onSelect(c.case_ref)}
        >
          <div className="queue-top">
            <span className={`pri pri-${c.priority}`}>P{c.priority}</span>
            <span className="mono small">{c.case_ref}</span>
            <span className={`pill ${c.action}`}>{c.action}</span>
          </div>
          <div className="queue-bottom">
            <span className="score">{c.score.toFixed(4)}</span>
            <span className="muted">{money(c.amount)}</span>
            {c.assigned_to && (
              <span className="muted small">{c.assigned_to}</span>
            )}
          </div>
        </li>
      ))}
    </ul>
  )
}

function Detail({ caseRef, onChanged }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [notes, setNotes] = useState('')

  const load = useCallback(async () => {
    if (!caseRef) return
    try {
      const d = await api.getCase(caseRef)
      setData(d)
      setNotes(d.notes || '')
      setError(null)
    } catch (err) {
      setError(err.message)
    }
  }, [caseRef])

  useEffect(() => {
    load()
  }, [load])

  if (!caseRef) {
    return <div className="empty">Select a case from the queue.</div>
  }
  if (error) return <div className="error">{error}</div>
  if (!data) return <div className="empty">Loading...</div>

  const reasons = data.explanation?.top_reasons || []
  const rules = data.explanation?.rules_fired || []
  const closed = data.status === 'closed'

  async function assign() {
    setBusy(true)
    try {
      await api.assignCase(caseRef)
      await load()
      onChanged()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function verdict(value) {
    setBusy(true)
    try {
      await api.submitVerdict(caseRef, value, notes)
      await load()
      onChanged()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="detail">
      <div className="detail-head">
        <div>
          <h2>{data.case_ref}</h2>
          <div className="muted small mono">{data.transaction_ref}</div>
        </div>
        <span className={`pill ${data.action}`}>{data.action}</span>
      </div>

      <div className="detail-stats">
        <div>
          <div className="stat-value">{data.score.toFixed(4)}</div>
          <div className="stat-label">score</div>
        </div>
        <div>
          <div className="stat-value">{money(data.amount)}</div>
          <div className="stat-label">amount</div>
        </div>
        <div>
          <div className="stat-value">P{data.priority}</div>
          <div className="stat-label">priority</div>
        </div>
        <div>
          <div className="stat-value small-val">{data.status}</div>
          <div className="stat-label">status</div>
        </div>
      </div>

      <section>
        <h3>Why the model flagged it</h3>
        {reasons.length === 0 && (
          <p className="muted small">
            No explanation stored. SHAP runs only on review and block
            decisions \u2014 explaining every approval would cost 40 ms on the
            common path for an explanation nobody reads.
          </p>
        )}
        {reasons.length > 0 && (
          <table className="shap">
            <tbody>
              {reasons.map((r) => (
                <tr key={r.feature}>
                  <td className="mono small">{r.feature}</td>
                  <td className="num">
                    {Number(r.value).toLocaleString('en-IN', {
                      maximumFractionDigits: 2,
                    })}
                  </td>
                  <td className="shap-bar-cell">
                    <div
                      className="shap-bar"
                      style={{
                        width: `${Math.min(
                          100,
                          (r.shap / (reasons[0]?.shap || 1)) * 100,
                        )}%`,
                      }}
                    />
                  </td>
                  <td className="num shap-val">+{r.shap.toFixed(3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {rules.length > 0 && (
        <section>
          <h3>Policy rules that fired</h3>
          <ul className="rules">
            {rules.map((r) => (
              <li key={r.rule}>
                <span className={`pill ${r.decision}`}>{r.decision}</span>
                <strong className="mono small"> {r.rule}</strong>
                <div className="muted small">{r.reason}</div>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section>
        <h3>Verdict</h3>
        {closed ? (
          <div className="closed-note">
            Closed as <strong>{data.verdict}</strong>
            {data.assigned_to && (
              <span className="muted"> by {data.assigned_to}</span>
            )}
            {data.notes && <div className="muted small">{data.notes}</div>}
          </div>
        ) : (
          <>
            {!data.assigned_to && (
              <button className="btn" onClick={assign} disabled={busy}>
                Assign to me
              </button>
            )}
            <textarea
              placeholder="Investigation notes (stored with the verdict)"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={3}
            />
            <div className="verdict-row">
              {VERDICTS.map((v) => (
                <button
                  key={v.value}
                  className={`btn verdict ${v.tone}`}
                  disabled={busy || !api.can('submit_verdict')}
                  onClick={() => verdict(v.value)}
                  title={v.note}
                >
                  {v.label}
                </button>
              ))}
            </div>
            <p className="muted small">
              This verdict is the training label the model relearns from.
              &quot;Inconclusive&quot; is recorded but never used \u2014 an
              analyst who could not decide has not said the transaction was
              legitimate.
            </p>
          </>
        )}
      </section>

      <section>
        <h3>Audit trail</h3>
        <ul className="audit">
          {(data.audit_trail || []).map((e, i) => (
            <li key={i}>
              <span className="muted small mono">{when(e.at)}</span>
              <strong> {e.event}</strong>
              <span className="muted"> by {e.actor}</span>
            </li>
          ))}
        </ul>
      </section>

      <div className="muted small">
        Model {data.model_version} &middot; {data.n_features} features stored
      </div>
    </div>
  )
}

export default function CaseQueue() {
  const [cases, setCases] = useState([])
  const [selected, setSelected] = useState(null)
  const [status, setStatus] = useState('open')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.listCases({ limit: 50, status })
      setCases(data.cases || [])
      setError(null)
      if (data.cases?.length && !data.cases.find((c) => c.case_ref === selected)) {
        setSelected(data.cases[0].case_ref)
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [status, selected])

  useEffect(() => {
    load()
  }, [status])

  return (
    <div className="cases">
      <div className="queue-pane">
        <div className="queue-head">
          <h2>Queue</h2>
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="open">Open</option>
            <option value="in_review">In review</option>
            <option value="closed">Closed</option>
          </select>
        </div>
        <div className="muted small queue-note">
          Sorted by priority, which is score &times; amount \u2014 a 0.95 on
          &#8377;50 matters less than a 0.40 on &#8377;200,000.
        </div>
        {error && <div className="error">{error}</div>}
        <Queue
          cases={cases}
          selected={selected}
          onSelect={setSelected}
          loading={loading}
        />
      </div>

      <div className="detail-pane">
        <Detail caseRef={selected} onChanged={load} />
      </div>
    </div>
  )
}
'''

p = Path("src/CaseQueue.jsx")
p.write_text(SRC, encoding="utf-8")
print("src/CaseQueue.jsx", p.stat().st_size, "bytes")
print("ends correctly:", SRC.rstrip().endswith("}"))