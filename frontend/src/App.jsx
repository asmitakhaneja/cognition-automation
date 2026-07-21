import React, { useCallback, useEffect, useRef, useState } from 'react'
import { fetchStatus, subscribeEvents, relativeTime, formatAcus } from './lib.js'

const CARD_FIELDS = [
  { key: 'total_triggered', label: 'Triggered' },
  { key: 'in_progress', label: 'In progress' },
  { key: 'finished', label: 'Finished' },
  { key: 'prs_opened', label: 'PRs opened' },
  { key: 'prs_merged', label: 'PRs merged' },
  { key: 'blocked_or_failed', label: 'Blocked/Failed' },
  { key: 'success_rate_pct', label: 'Success rate', suffix: '%' },
  { key: 'total_acus', label: 'Total ACUs' },
  { key: 'avg_acus_per_fix', label: 'ACUs / fix' },
]

function SummaryCards({ summary }) {
  return (
    <div className="cards">
      {CARD_FIELDS.map(({ key, label, suffix }) => {
        const val = summary?.[key]
        const has = val !== null && val !== undefined
        return (
          <div className="card" key={key}>
            <div className="num">{has ? `${val}${suffix && has ? suffix : ''}` : '—'}</div>
            <div className="label">{label}</div>
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

function SessionRow({ r }) {
  const [open, setOpen] = useState(false)
  const n = r.issue_number
  const messages = r.messages || []
  const msgCount = messages.length
  const tools = [...(r.tools_and_frameworks || []), ...(r.programming_languages || [])].join(', ')
  const conf = r.classification_confidence

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
      </tr>
      {open && (
        <tr>
          <td colSpan={9} className="log-cell">
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

  return (
    <>
      <h1>Devin Remediation Dashboard</h1>
      <p className="subtitle">
        Repo: {summary?.repo || data?.repo || '…'} · Updates in real-time
        <span className={`conn ${live ? 'conn-live' : 'conn-off'}`}>{live ? '● live' : '○ offline'}</span>
      </p>

      {error && <p style={{ color: '#f87171' }}>Failed to load: {error}</p>}

      <SummaryCards summary={summary} />

      <table>
        <thead>
          <tr>
            <th>Issue</th><th>Title</th><th>Category</th><th>Started</th>
            <th>Status</th><th>PR</th><th>PR Status</th><th>ACUs</th><th>Devin Session</th>
          </tr>
        </thead>
        <tbody>
          {data === null ? (
            <tr><td colSpan={9} className="loading">Loading…</td></tr>
          ) : records.length ? (
            records.map((r) => <SessionRow key={r.issue_number} r={r} />)
          ) : (
            <tr><td colSpan={9} className="empty">No issues triggered yet.</td></tr>
          )}
        </tbody>
      </table>
    </>
  )
}
