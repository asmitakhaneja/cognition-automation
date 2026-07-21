interface KpiProps {
  label: string;
  value: string;
  sublabel?: string;
  accent?: string;
}

export function Kpi({ label, value, sublabel, accent }: KpiProps) {
  return (
    <div className="kpi-card">
      <div className="kpi-label">{label}</div>
      <div className="kpi-value" style={accent ? { color: accent } : undefined}>
        {value}
      </div>
      {sublabel && <div className="kpi-sub">{sublabel}</div>}
    </div>
  );
}
