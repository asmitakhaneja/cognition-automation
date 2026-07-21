export function formatNumber(n: number): string {
  return n.toLocaleString(undefined, { maximumFractionDigits: 0 });
}

export function formatAcus(n: number): string {
  return n.toLocaleString(undefined, { maximumFractionDigits: 1 });
}

export function formatPct(fraction: number): string {
  return `${(fraction * 100).toFixed(1)}%`;
}

export function formatDate(ts: number): string {
  return new Date(ts * 1000).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function shortDate(iso: string): string {
  const d = new Date(`${iso}T00:00:00Z`);
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function prettyLabel(value: string): string {
  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

const STATUS_COLORS: Record<string, string> = {
  exit: "#22c55e",
  running: "#38bdf8",
  suspended: "#f59e0b",
  error: "#ef4444",
  new: "#a78bfa",
  claimed: "#818cf8",
  resuming: "#2dd4bf",
};

export function statusColor(status: string): string {
  return STATUS_COLORS[status] ?? "#94a3b8";
}

export function mergedPrUrl(session: {
  pull_requests: { url: string; state: string | null }[];
}): { url: string; state: string } | null {
  if (session.pull_requests.length === 0) return null;
  const merged = session.pull_requests.find(
    (p) => (p.state ?? "").toLowerCase() === "merged",
  );
  const pr = merged ?? session.pull_requests[0];
  return { url: pr.url, state: pr.state ?? "open" };
}

export const CHART_COLORS = [
  "#6366f1",
  "#22c55e",
  "#f59e0b",
  "#ec4899",
  "#38bdf8",
  "#a78bfa",
  "#f43f5e",
  "#14b8a6",
  "#eab308",
  "#94a3b8",
];
