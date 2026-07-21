import React from 'react'
import { buildCharts } from './lib.js'

const STATUS_COLORS = {
  finished: '#4ade80',
  running: '#facc15',
  suspended: '#fb923c',
  blocked: '#f87171',
  expired: '#f87171',
  stopped: '#f87171',
  unknown: '#64748b',
}
const CATEGORY_COLORS = {
  security: '#f87171',
  dependency: '#60a5fa',
  tests: '#c084fc',
  quality: '#4ade80',
}

// SVG pie chart with a legend. `data` = [{label, value}].
function PieChart({ data, colorFor }) {
  const total = data.reduce((s, d) => s + d.value, 0)
  if (!total) return <p className="chart-empty">No data yet.</p>
  const cx = 60, cy = 60, r = 54
  let angle = -Math.PI / 2 // start at 12 o'clock
  const arc = (value) => {
    const slice = (value / total) * Math.PI * 2
    const x1 = cx + r * Math.cos(angle)
    const y1 = cy + r * Math.sin(angle)
    angle += slice
    const x2 = cx + r * Math.cos(angle)
    const y2 = cy + r * Math.sin(angle)
    const large = slice > Math.PI ? 1 : 0
    // full circle can't be drawn with a single arc — draw two half circles
    if (value === total) {
      return `M ${cx} ${cy - r} A ${r} ${r} 0 1 1 ${cx - 0.01} ${cy - r} Z`
    }
    return `M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2} Z`
  }
  return (
    <div className="pie-wrap">
      <svg className="pie" viewBox="0 0 120 120" width="120" height="120" role="img">
        {data.map((d) => (
          <path key={d.label} d={arc(d.value)} fill={colorFor ? colorFor(d.label) : '#60a5fa'}
            stroke="#1e293b" strokeWidth="1.5" />
        ))}
      </svg>
      <ul className="pie-legend">
        {data.map((d) => (
          <li key={d.label}>
            <span className="pie-dot" style={{ background: colorFor ? colorFor(d.label) : '#60a5fa' }} />
            <span className="pie-name">{d.label}</span>
            <span className="pie-count">{d.value} ({Math.round((d.value / total) * 100)}%)</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

// SVG funnel: stacked centered bars that narrow toward the outcome.
function Funnel({ data }) {
  const max = Math.max(...data.map((d) => d.value), 1)
  const W = 260
  const rowH = 46
  return (
    <svg className="funnel" viewBox={`0 0 ${W} ${data.length * rowH}`} width="100%" role="img">
      {data.map((d, i) => {
        const w = Math.max((d.value / max) * W, 42)
        const x = (W - w) / 2
        const y = i * rowH + 4
        const shades = ['#1d4ed8', '#2563eb', '#7c3aed']
        return (
          <g key={d.label}>
            <rect x={x} y={y} width={w} height={rowH - 12} rx="6" fill={shades[i % shades.length]} />
            <text x={W / 2} y={y + (rowH - 12) / 2 + 1} textAnchor="middle" dominantBaseline="middle"
              fontSize="12" fontWeight="700" fill="#e2e8f0">{d.value}</text>
            <text x={W / 2} y={y + (rowH - 12) / 2 + 14} textAnchor="middle" dominantBaseline="middle"
              fontSize="9" fill="#cbd5e1">{d.label}</text>
          </g>
        )
      })}
    </svg>
  )
}

function ChartCard({ title, subtitle, children }) {
  return (
    <div className="chart-card">
      <div className="chart-title">{title}</div>
      {subtitle && <div className="chart-sub">{subtitle}</div>}
      {children}
    </div>
  )
}

export default function Charts({ records, summary }) {
  const { funnel, byStatus, byCategory } = buildCharts(records, summary)
  return (
    <div className="charts">
      <ChartCard title="Remediation funnel" subtitle="Issue → PR → merged">
        <Funnel data={funnel} />
      </ChartCard>
      <ChartCard title="Sessions by status" subtitle="Where work stands right now">
        <PieChart data={byStatus} colorFor={(l) => STATUS_COLORS[l] || '#64748b'} />
      </ChartCard>
      <ChartCard title="Issues by category" subtitle="What kind of work Devin handles">
        <PieChart data={byCategory} colorFor={(l) => CATEGORY_COLORS[l] || '#60a5fa'} />
      </ChartCard>
    </div>
  )
}
