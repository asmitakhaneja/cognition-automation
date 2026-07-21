import { useEffect, useState } from "react";
import { fetchOverview } from "./api";
import { AutomationPanel } from "./components/AutomationPanel";
import { ActivityChart, CostChart, Donut, HBar } from "./components/Charts";
import { Kpi } from "./components/Kpi";
import { SessionDrawer } from "./components/SessionDrawer";
import { SessionsTable } from "./components/SessionsTable";
import type { Overview, Session } from "./types";
import { formatAcus, formatNumber, formatPct } from "./utils";

const RANGES = [7, 14, 30, 60, 90];

export function App() {
  const [days, setDays] = useState(30);
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<Session | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    fetchOverview(days)
      .then((d) => active && setData(d))
      .catch((e: Error) => active && setError(e.message))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [days]);

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" />
          <div>
            <h1>Devin Observability</h1>
            <p>Is it working? Progress, cost & activity at a glance.</p>
          </div>
        </div>
        <div className="controls">
          {data?.is_demo && <span className="demo-pill">Demo data</span>}
          <div className="range-select">
            {RANGES.map((r) => (
              <button
                key={r}
                className={r === days ? "active" : ""}
                onClick={() => setDays(r)}
              >
                {r}d
              </button>
            ))}
          </div>
        </div>
      </header>

      {error && (
        <div className="banner error">
          Failed to load data: {error}
        </div>
      )}

      {loading && !data && <div className="banner">Loading dashboard…</div>}

      {data && (
        <main className="content">
          <section className="kpi-row">
            <Kpi
              label="Sessions"
              value={formatNumber(data.kpis.total_sessions)}
              sublabel={`${data.kpis.active_users} active users`}
            />
            <Kpi
              label="PRs created"
              value={formatNumber(data.kpis.prs_created)}
              sublabel={`${formatNumber(data.kpis.prs_merged)} merged`}
              accent="#22c55e"
            />
            <Kpi
              label="PR merge rate"
              value={formatPct(data.kpis.pr_merge_rate)}
              sublabel="of created PRs"
              accent="#22c55e"
            />
            <Kpi
              label="Success rate"
              value={formatPct(data.kpis.success_rate)}
              sublabel="sessions finished cleanly"
            />
            <Kpi
              label="Total ACUs"
              value={formatAcus(data.kpis.total_acus)}
              sublabel={`${formatAcus(data.kpis.avg_acus_per_session)} avg / session`}
              accent="#f59e0b"
            />
            <Kpi
              label="ACU / merged PR"
              value={formatAcus(data.kpis.acus_per_merged_pr)}
              sublabel="cost efficiency"
              accent="#f59e0b"
            />
          </section>

          <section className="grid two">
            <Card title="Delivery over time" subtitle="Sessions vs. PRs merged per day">
              <ActivityChart data={data.timeseries} />
            </Card>
            <Card title="Cost over time" subtitle="ACU consumption by product">
              <CostChart data={data.timeseries} />
            </Card>
          </section>

          <section className="grid three">
            <Card title="Session outcomes" subtitle="By status">
              <Donut data={data.by_status} colorByStatus />
            </Card>
            <Card title="Where work comes from" subtitle="By origin">
              <Donut data={data.by_origin} />
            </Card>
            <Card title="What Devin works on" subtitle="By use-case category">
              <HBar data={data.by_category} metric="count" color="#a78bfa" />
            </Card>
          </section>

          <section className="grid two">
            <Card title="Top spenders" subtitle="ACU by user">
              <HBar data={data.by_user} metric="acus" color="#f59e0b" />
            </Card>
            <Card title="Busiest repositories" subtitle="Sessions by repo">
              <HBar data={data.by_repo} metric="count" color="#38bdf8" />
            </Card>
          </section>

          <section className="grid one">
            <div className="card">
              <AutomationPanel />
            </div>
          </section>

          <section className="grid one">
            <Card
              title="Recent activity"
              subtitle="Latest sessions — click a row for the full log"
            >
              <SessionsTable sessions={data.recent_sessions} onSelect={setSelected} />
            </Card>
          </section>

          <footer className="foot">
            {data.is_demo
              ? "Showing built-in demo data. Set DEVIN_API_KEY + DEVIN_ORG_ID on the backend to load live data."
              : "Live data from the Devin organization API."}{" "}
            · Last {data.range_days} days
          </footer>
        </main>
      )}

      {selected && (
        <SessionDrawer session={selected} onClose={() => setSelected(null)} />
      )}
    </div>
  );
}

function Card({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="card">
      <div className="card-head">
        <h3>{title}</h3>
        {subtitle && <span>{subtitle}</span>}
      </div>
      {children}
    </div>
  );
}
