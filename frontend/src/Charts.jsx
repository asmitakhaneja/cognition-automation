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

// Horizontal labeled bar chart. `data` = [{label, value}].
function BarChart({ data, colorFor, unit }) {
  if (!data.length) return <p className="chart-empty">No data yet.</p>
  const max = Math.max(...data.map((d) => d.value), 1)
  return (
    <div className="bars">
      {data.map((d) => (
        <div className="bar-row" key={d.label}>
          <span className="bar-label">{d.label}</span>
          <div className="bar-track">
            <div
              className="bar-fill"
              style={{ width: `${(d.value / max) * 100}%`, background: colorFor ? colorFor(d.label) : '#60a5fa' }}
            />
          </div>
          <span className="bar-value">{d.value}{unit || ''}</span>
        </div>
      ))}
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
  const { funnel, byStatus, byCategory, acusByIssue } = buildCharts(records, summary)
  return (
    <div className="charts">
      <ChartCard title="Remediation funnel" subtitle="Issue → PR → merged">
        <Funnel data={funnel} />
      </ChartCard>
      <ChartCard title="Sessions by status" subtitle="Where work stands right now">
        <BarChart data={byStatus} colorFor={(l) => STATUS_COLORS[l] || '#64748b'} />
      </ChartCard>
      <ChartCard title="Issues by category" subtitle="What kind of work Devin handles">
        <BarChart data={byCategory} colorFor={(l) => CATEGORY_COLORS[l] || '#60a5fa'} />
      </ChartCard>
      <ChartCard title="Compute per issue" subtitle="ACUs consumed per session">
        <BarChart data={acusByIssue} unit=" ACU" />
      </ChartCard>
    </div>
  )
}
