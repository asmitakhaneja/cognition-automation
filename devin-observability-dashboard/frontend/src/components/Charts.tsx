import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { NamedCount, TimePoint } from "../types";
import { CHART_COLORS, prettyLabel, shortDate, statusColor } from "../utils";

const AXIS = { stroke: "#64748b", fontSize: 12 };
const GRID = "#1e293b";

const tooltipStyle = {
  background: "#0f172a",
  border: "1px solid #334155",
  borderRadius: 8,
  color: "#e2e8f0",
  fontSize: 12,
};

export function ActivityChart({ data }: { data: TimePoint[] }) {
  return (
    <ResponsiveContainer width="100%" height={280}>
      <ComposedChart data={data} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="date" tickFormatter={shortDate} tick={AXIS} tickLine={false} />
        <YAxis tick={AXIS} tickLine={false} axisLine={false} />
        <Tooltip contentStyle={tooltipStyle} labelFormatter={shortDate} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Bar dataKey="sessions" name="Sessions" fill="#6366f1" radius={[3, 3, 0, 0]} />
        <Line
          type="monotone"
          dataKey="prs_merged"
          name="PRs merged"
          stroke="#22c55e"
          strokeWidth={2}
          dot={false}
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

export function CostChart({ data }: { data: TimePoint[] }) {
  const series: { key: keyof TimePoint; name: string; color: string }[] = [
    { key: "acus_devin", name: "Devin", color: "#6366f1" },
    { key: "acus_cascade", name: "Cascade", color: "#22c55e" },
    { key: "acus_terminal", name: "Terminal", color: "#f59e0b" },
    { key: "acus_review", name: "Review", color: "#ec4899" },
  ];
  return (
    <ResponsiveContainer width="100%" height={280}>
      <AreaChart data={data} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="date" tickFormatter={shortDate} tick={AXIS} tickLine={false} />
        <YAxis tick={AXIS} tickLine={false} axisLine={false} />
        <Tooltip contentStyle={tooltipStyle} labelFormatter={shortDate} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        {series.map((s) => (
          <Area
            key={s.key}
            type="monotone"
            dataKey={s.key}
            name={s.name}
            stackId="acus"
            stroke={s.color}
            fill={s.color}
            fillOpacity={0.75}
          />
        ))}
      </AreaChart>
    </ResponsiveContainer>
  );
}

interface DonutProps {
  data: NamedCount[];
  colorByStatus?: boolean;
}

export function Donut({ data, colorByStatus }: DonutProps) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <PieChart>
        <Pie
          data={data}
          dataKey="count"
          nameKey="name"
          innerRadius={55}
          outerRadius={95}
          paddingAngle={2}
        >
          {data.map((entry, i) => (
            <Cell
              key={entry.name}
              fill={colorByStatus ? statusColor(entry.name) : CHART_COLORS[i % CHART_COLORS.length]}
            />
          ))}
        </Pie>
        <Tooltip
          contentStyle={tooltipStyle}
          formatter={(v: number, n: string) => [v, prettyLabel(n)]}
        />
        <Legend
          wrapperStyle={{ fontSize: 12 }}
          formatter={(v: string) => prettyLabel(v)}
        />
      </PieChart>
    </ResponsiveContainer>
  );
}

interface HBarProps {
  data: NamedCount[];
  metric: "count" | "acus";
  color?: string;
}

export function HBar({ data, metric, color = "#6366f1" }: HBarProps) {
  const rows = [...data].sort((a, b) => b[metric] - a[metric]);
  const height = Math.max(200, rows.length * 34);
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart
        data={rows}
        layout="vertical"
        margin={{ top: 4, right: 16, left: 8, bottom: 4 }}
      >
        <CartesianGrid stroke={GRID} horizontal={false} />
        <XAxis type="number" tick={AXIS} tickLine={false} axisLine={false} />
        <YAxis
          type="category"
          dataKey="name"
          tick={{ ...AXIS, width: 140 }}
          tickFormatter={prettyLabel}
          width={150}
          tickLine={false}
          axisLine={false}
        />
        <Tooltip
          contentStyle={tooltipStyle}
          formatter={(v: number) => [metric === "acus" ? `${v} ACU` : v, ""]}
          labelFormatter={prettyLabel}
        />
        <Bar dataKey={metric} fill={color} radius={[0, 3, 3, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
