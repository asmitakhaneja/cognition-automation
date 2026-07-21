// Data fetching + formatting helpers for the dashboard.

export async function fetchStatus() {
  const res = await fetch('/status', { headers: { Accept: 'application/json' } })
  if (!res.ok) throw new Error(`/status returned ${res.status}`)
  return res.json()
}

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
