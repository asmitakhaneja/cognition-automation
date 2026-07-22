// Data fetching + formatting helpers for the dashboard.

export async function fetchStatus() {
  const res = await fetch('/status', { headers: { Accept: 'application/json' } })
  if (!res.ok) throw new Error(`/status returned ${res.status}`)
  return res.json()
}

// Ask the backend to terminate the Devin session for an issue. The backend
// calls the Devin terminate-session API and returns the updated record.
export async function terminateSession(issueNumber) {
  const res = await fetch(`/session/${issueNumber}/terminate`, { method: 'POST' })
  if (!res.ok) {
    let detail = `terminate returned ${res.status}`
    try {
      const body = await res.json()
      if (body?.detail) detail = body.detail
    } catch {}
    throw new Error(detail)
  }
  return res.json()
}

// Statuses for which a session is already over and cannot be terminated.
export const TERMINAL_STATUSES = ['finished', 'blocked', 'expired', 'stopped', 'exit', 'error']

// Subscribe to backend Server-Sent Events. Returns an unsubscribe function.
// `onEvent` fires on every status change; `onState` reports connection state.
export function subscribeEvents(onEvent, onState) {
  const es = new EventSource('/events')
  es.onopen = () => onState?.(true)
  es.onmessage = () => onEvent?.()
  es.onerror = () => onState?.(false)
  return () => es.close()
}

export function relativeTime(ts) {
  if (!ts) return '—'
  const sec = Math.floor(Date.now() / 1000 - ts)
  if (sec < 60) return `${sec}s ago`
  if (sec < 3600) return `${Math.floor(sec / 60)}m ago`
  if (sec < 86400) return `${Math.floor(sec / 3600)}h ago`
  return `${Math.floor(sec / 86400)}d ago`
}

export function formatAcus(acus) {
  if (acus === null || acus === undefined) return '—'
  return String(Math.round(Number(acus) * 10) / 10)
}

// Roll the raw records + summary into the datasets the charts render. Everything
// here is derived from parameters the backend already captures per session
// (status, category, pr_status, acus_consumed) — no new backend data needed.
export function buildCharts(records, summary) {
  const byKey = (getter) => {
    const counts = {}
    for (const r of records) {
      const k = getter(r)
      if (!k) continue
      counts[k] = (counts[k] || 0) + 1
    }
    return Object.entries(counts)
      .map(([label, value]) => ({ label, value }))
      .sort((a, b) => b.value - a.value)
  }

  const funnel = [
    { label: 'Picked up', value: summary?.total_triggered || 0 },
    { label: 'Fixes proposed', value: summary?.prs_opened || 0 },
    { label: 'Fixes shipped', value: summary?.prs_merged || 0 },
  ]

  const acusByIssue = records
    .filter((r) => r.acus_consumed !== null && r.acus_consumed !== undefined)
    .map((r) => ({ label: `#${r.issue_number}`, value: Math.round(Number(r.acus_consumed) * 10) / 10 }))

  return {
    funnel,
    byStatus: byKey((r) => r.status),
    byCategory: byKey((r) => r.category),
    acusByIssue,
  }
}

