import { useMemo, useState } from "react";
import type { Session } from "../types";
import { formatAcus, formatDate, mergedPrUrl, prettyLabel, statusColor } from "../utils";

interface Props {
  sessions: Session[];
  onSelect: (session: Session) => void;
}

export function SessionsTable({ sessions, onSelect }: Props) {
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");

  const statuses = useMemo(
    () => ["all", ...Array.from(new Set(sessions.map((s) => s.status)))],
    [sessions],
  );

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return sessions.filter((s) => {
      if (statusFilter !== "all" && s.status !== statusFilter) return false;
      if (!q) return true;
      return (
        (s.title ?? "").toLowerCase().includes(q) ||
        (s.user_name ?? "").toLowerCase().includes(q) ||
        (s.repo ?? "").toLowerCase().includes(q) ||
        (s.category ?? "").toLowerCase().includes(q)
      );
    });
  }, [sessions, query, statusFilter]);

  return (
    <div>
      <div className="table-controls">
        <input
          className="search"
          placeholder="Search title, user, repo, category…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          {statuses.map((s) => (
            <option key={s} value={s}>
              {s === "all" ? "All statuses" : prettyLabel(s)}
            </option>
          ))}
        </select>
      </div>

      <div className="table-scroll">
        <table className="sessions-table">
          <thead>
            <tr>
              <th>Session</th>
              <th>Status</th>
              <th>User</th>
              <th>Category</th>
              <th>Origin</th>
              <th className="num">ACU</th>
              <th>PR</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((s) => {
              const pr = mergedPrUrl(s);
              return (
                <tr key={s.session_id} onClick={() => onSelect(s)}>
                  <td className="title-cell">{s.title ?? s.session_id}</td>
                  <td>
                    <span className="dot" style={{ background: statusColor(s.status) }} />
                    {prettyLabel(s.status)}
                  </td>
                  <td>{s.user_name ?? "—"}</td>
                  <td>{s.category ? prettyLabel(s.category) : "—"}</td>
                  <td>{s.origin ? prettyLabel(s.origin) : "—"}</td>
                  <td className="num">{formatAcus(s.acus_consumed)}</td>
                  <td>
                    {pr ? (
                      <a
                        href={pr.url}
                        target="_blank"
                        rel="noreferrer"
                        onClick={(e) => e.stopPropagation()}
                        className={`pr-badge pr-${pr.state}`}
                      >
                        {pr.state}
                      </a>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="muted">{formatDate(s.created_at)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {filtered.length === 0 && <div className="empty">No sessions match your filters.</div>}
      </div>
    </div>
  );
}
