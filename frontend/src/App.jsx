import React, { useCallback, useEffect, useRef, useState } from 'react'
import { fetchStatus, subscribeEvents, relativeTime, formatAcus, terminateSession, TERMINAL_STATUSES } from './lib.js'
import Charts from './Charts.jsx'
import { Icon } from './icons.jsx'

const CARD_FIELDS = [
  { key: 'total_triggered', label: 'Issues Picked Up', hint: 'Total issues Devin was triggered on', icon: 'inbox', accent: 'blue' },
  { key: 'in_progress', label: 'Currently Working', hint: 'Sessions still running', icon: 'activity', accent: 'amber' },
  { key: 'finished', label: 'Completed', hint: 'Sessions that reached a terminal state', icon: 'check', accent: 'green' },
  { key: 'prs_opened', label: 'Fixes Proposed', hint: 'Pull requests opened', icon: 'pr', accent: 'blue' },
  { key: 'prs_merged', label: 'Fixes Shipped', hint: 'Pull requests merged to the codebase', icon: 'merge', accent: 'violet' },
  { key: 'blocked_or_failed', label: 'Needs Attention', hint: 'Blocked, expired or stopped sessions', icon: 'alert', accent: 'red' },
  { key: 'success_rate_pct', label: 'Fix Success Rate', hint: '% of issues that produced a PR', suffix: '%', icon: 'target', accent: 'green' },
  { key: 'total_acus', label: 'Total Compute (ACUs)', hint: 'Total Agent Compute Units consumed', icon: 'cpu', accent: 'violet' },
  { key: 'avg_acus_per_fix', label: 'Compute per Fix', hint: 'Average ACUs per delivered PR', icon: 'gauge', accent: 'blue' },
]

function SummaryCards({ summary }) {
  return (
    <div className="cards">
      {CARD_FIELDS.map(({ key, label, suffix, hint, icon, accent }) => {
        const val = summary?.[key]
        const has = val !== null && val !== undefined
        return (
          <div className={`card accent-${accent}`} key={key} title={hint}>
            <div className="card-icon"><Icon name={icon} /></div>
            <div className="card-body">
              <div className="num">{has ? `${val}${suffix && has ? suffix : ''}` : '—'}</div>
              <div className="label">{label}</div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

function MessageBubble({ msg }) {
  const [expanded, setExpanded] = useState(false)
  const [clamped, setClamped] = useState(false)
  const textRef = useRef(null)

  const src = msg.source || 'unknown'
  const isUser = src === 'user'
  const label = isUser ? 'You' : 'Devin'
  const avatarLabel = isUser ? 'You' : 'Dev'
  const text = msg.message || msg.content || ''

  useEffect(() => {
    const el = textRef.current
    if (el) setClamped(el.scrollHeight > el.clientHeight + 2)
  }, [text])

  return (
    <div className={`bubble-row ${isUser ? 'bubble-user' : 'bubble-devin'}`}>
      <div className={`avatar ${isUser ? 'avatar-user' : 'avatar-devin'}`}>{avatarLabel}</div>
      <div className="bubble">
        <div className="bubble-meta">
          <strong>{label}</strong>
          {msg.created_at ? <span className="ts-inline">{msg.created_at}</span> : null}
        </div>
        <div ref={textRef} className={`bubble-text${expanded ? ' expanded' : ''}`}>{text}</div>
        {(clamped || expanded) && (
          <button className="expand-btn" onClick={() => setExpanded((e) => !e)}>
            {expanded ? 'Show less' : 'Show more'}
          </button>
        )}
      </div>
    </div>
  )
}

function SessionRow({ r, onChanged }) {
  const [open, setOpen] = useState(false)
  const [terminating, setTerminating] = useState(false)
  const [termError, setTermError] = useState(null)
  const n = r.issue_number
  const messages = r.messages || []
  const msgCount = messages.length
  const tools = [...(r.tools_and_frameworks || []), ...(r.programming_languages || [])].join(', ')
  const conf = r.classification_confidence
  const isActive = !!r.session_id && !TERMINAL_STATUSES.includes(r.status)

  const handleTerminate = async (e) => {
    e.stopPropagation()
    if (terminating) return
    if (!window.confirm(`Terminate the Devin session for issue #${n}? This cannot be undone.`)) return
    setTerminating(true)
    setTermError(null)
    try {
      await terminateSession(n)
      onChanged?.()
    } catch (err) {
      setTermError(err.message)
    } finally {
      setTerminating(false)
    }
  }

  return (
    <>
      <tr data-issue={n} title="Click to toggle session log" onClick={() => setOpen((o) => !o)}>
        <td>#{n}</td>
        <td>{r.title || ''}</td>
        <td>
          <span className="tag">{r.category || ''}</span>
          {conf !== null && conf !== undefined && (
            <><br /><small className="detail">conf: {Math.round(conf * 100) / 100}</small></>
          )}
          {tools && (<><br /><small className="tools">{tools}</small></>)}
        </td>
        <td className="ts">{relativeTime(r.created_at)}</td>
        <td className={`status-${r.status || 'unknown'}`}>
          {r.status || 'unknown'}
          {r.status_detail && (<><br /><small className="detail">{r.status_detail}</small></>)}
        </td>
        <td>{r.pr_url ? <a href={r.pr_url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>PR ↗</a> : '—'}</td>
        <td><span className={`tag pr-${r.pr_status || ''}`}>{r.pr_status || '—'}</span></td>
        <td className="ts">{formatAcus(r.acus_consumed)}</td>
        <td>
          {r.session_url ? (
            <a href={r.session_url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>
              {msgCount ? <span className="msg-badge">{msgCount}</span> : null}session ↗
            </a>
          ) : '—'} ▶
        </td>
        <td className="actions-cell" onClick={(e) => e.stopPropagation()}>
          {r.session_id ? (
            <button
              className="terminate-btn"
              onClick={handleTerminate}
              disabled={!isActive || terminating}
              title={isActive ? 'Terminate this Devin session' : 'Session already ended'}
            >
              {terminating ? 'Terminating…' : isActive ? 'Terminate' : 'Terminated'}
            </button>
          ) : (
            <span className="detail">—</span>
          )}
          {termError && <div className="term-error" title={termError}>failed</div>}
        </td>
      </tr>
      {open && (
        <tr>
          <td colSpan={10} className="log-cell">
            <div className="log-panel">
              <div className="log-header">
                <span><strong>Session log</strong> · issue #{n} · {msgCount} message{msgCount !== 1 ? 's' : ''}</span>
                <span className="log-close" onClick={(e) => { e.stopPropagation(); setOpen(false) }}>✕ close</span>
              </div>
              <div className="log-messages">
                {msgCount ? (
                  messages.map((m, i) => <MessageBubble key={i} msg={m} />)
                ) : (
                  <p style={{ color: '#475569', fontSize: '0.8rem', textAlign: 'center', padding: '1rem 0' }}>
                    No messages yet.
                  </p>
                )}
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  )
}

export default function App() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [live, setLive] = useState(false)

  const load = useCallback(async () => {
    try {
      setData(await fetchStatus())
      setError(null)
    } catch (e) {
      setError(e.message)
    }
  }, [])

  useEffect(() => {
    load()
    const unsub = subscribeEvents(load, setLive)
    return unsub
  }, [load])

  const summary = data?.summary
  const records = data?.records || []

  const repo = summary?.repo || data?.repo || '…'

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark">D</div>
          <div>
            <h1>Remediation Dashboard</h1>
            <p className="subtitle">Autonomous issue remediation for <span className="repo">{repo}</span></p>
          </div>
        </div>
        <span className={`conn ${live ? 'conn-live' : 'conn-off'}`}>
          <span className="conn-dot" />{live ? 'Live' : 'Offline'}
        </span>
      </header>

      {error && <p className="error-banner">Failed to load: {error}</p>}

      <section className="panel">
        <h2 className="section-title">Overview</h2>
        <SummaryCards summary={summary} />
      </section>

      {records.length > 0 && (
        <section className="panel">
          <h2 className="section-title">Analytics</h2>
          <Charts records={records} summary={summary} />
        </section>
      )}

      <section className="panel">
        <h2 className="section-title">Sessions{records.length ? <span className="count-pill">{records.length}</span> : null}</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Issue</th><th>Title</th><th>Category</th><th>Started</th>
                <th>Status</th><th>PR</th><th>PR Status</th><th>ACUs</th><th>Devin Session</th><th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {data === null ? (
                <tr><td colSpan={10} className="loading">Loading…</td></tr>
              ) : records.length ? (
                records.map((r) => <SessionRow key={r.issue_number} r={r} onChanged={load} />)
              ) : (
                <tr><td colSpan={10} className="empty">No issues triggered yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
