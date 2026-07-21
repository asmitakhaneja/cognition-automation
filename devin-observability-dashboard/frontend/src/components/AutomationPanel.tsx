import { useEffect, useRef, useState } from "react";
import { fetchAutomation } from "../api";
import type { AutomationStatus } from "../types";
import {
  automationStatusColor,
  formatDate,
  formatDuration,
  prettyLabel,
} from "../utils";

const REFRESH_MS = 8000;

export function AutomationPanel() {
  const [data, setData] = useState<AutomationStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pulse, setPulse] = useState(false);
  const timer = useRef<number | null>(null);

  useEffect(() => {
    let active = true;
    const load = () => {
      fetchAutomation()
        .then((d) => {
          if (!active) return;
          setData(d);
          setError(null);
          setPulse(true);
          window.setTimeout(() => active && setPulse(false), 600);
        })
        .catch((e: Error) => active && setError(e.message));
    };
    load();
    timer.current = window.setInterval(load, REFRESH_MS);
    return () => {
      active = false;
      if (timer.current) window.clearInterval(timer.current);
    };
  }, []);

  if (error) {
    return <div className="banner error">Automation unavailable: {error}</div>;
  }
  if (!data) {
    return <div className="banner">Loading automation…</div>;
  }

  const s = data.summary;
  return (
    <div className="automation">
      <div className="automation-head">
        <div>
          <h3>
            Automation
            <span className={`live-dot ${pulse ? "pulse" : ""}`} />
            <span className="live-label">live</span>
          </h3>
          <span>
            GitHub <code>{data.trigger_label}</code> issues on{" "}
            <code>{data.repo}</code> → Devin sessions · refreshes every 8s
          </span>
        </div>
        {!data.enabled && (
          <span className="demo-pill">
            {data.is_demo ? "Demo data" : "Not configured"}
          </span>
        )}
      </div>

      <div className="automation-cards">
        <Stat label="Triggered" value={s.total_triggered} />
        <Stat label="In progress" value={s.in_progress} accent="#38bdf8" />
        <Stat label="Finished" value={s.finished} accent="#22c55e" />
        <Stat label="PRs opened" value={s.prs_opened} accent="#22c55e" />
        <Stat
          label="Blocked/failed"
          value={s.blocked_or_failed}
          accent="#ef4444"
        />
        <Stat
          label="Success rate"
          value={s.success_rate_pct === null ? "—" : `${s.success_rate_pct}%`}
        />
        <Stat
          label="Avg time to PR"
          value={formatDuration(s.avg_time_to_finish_sec)}
        />
      </div>

      <table className="table automation-table">
        <thead>
          <tr>
            <th>Issue</th>
            <th>Title</th>
            <th>Category</th>
            <th>Status</th>
            <th>PR</th>
            <th>Session</th>
            <th>Triggered</th>
          </tr>
        </thead>
        <tbody>
          {data.records.length === 0 && (
            <tr>
              <td colSpan={7} className="empty">
                No issues triggered yet.
              </td>
            </tr>
          )}
          {data.records
            .slice()
            .reverse()
            .map((r) => (
              <tr key={r.issue_number}>
                <td>#{r.issue_number}</td>
                <td className="title-cell">{r.title ?? "—"}</td>
                <td>
                  {r.category ? (
                    <span className="badge">{prettyLabel(r.category)}</span>
                  ) : (
                    "—"
                  )}
                </td>
                <td>
                  <span
                    className="status-dot"
                    style={{ background: automationStatusColor(r.status) }}
                  />
                  {prettyLabel(r.status)}
                </td>
                <td>
                  {r.pr_url ? (
                    <a href={r.pr_url} target="_blank" rel="noreferrer">
                      PR ↗
                    </a>
                  ) : (
                    "—"
                  )}
                </td>
                <td>
                  {r.session_url ? (
                    <a href={r.session_url} target="_blank" rel="noreferrer">
                      session ↗
                    </a>
                  ) : (
                    "—"
                  )}
                </td>
                <td>{r.created_at ? formatDate(r.created_at) : "—"}</td>
              </tr>
            ))}
        </tbody>
      </table>
    </div>
  );
}

function Stat({
  label,
  value,
  accent,
}: {
  label: string;
  value: number | string;
  accent?: string;
}) {
  return (
    <div className="automation-stat">
      <div className="num" style={accent ? { color: accent } : undefined}>
        {value}
      </div>
      <div className="label">{label}</div>
    </div>
  );
}
