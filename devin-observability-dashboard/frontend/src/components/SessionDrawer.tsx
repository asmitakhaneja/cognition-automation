import { useEffect, useState } from "react";
import { fetchMessages } from "../api";
import type { Message, Session } from "../types";
import { formatAcus, formatDate, prettyLabel, statusColor } from "../utils";

interface Props {
  session: Session;
  onClose: () => void;
}

export function SessionDrawer({ session, onClose }: Props) {
  const [messages, setMessages] = useState<Message[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setMessages(null);
    setError(null);
    fetchMessages(session.session_id)
      .then((r) => {
        if (active) setMessages(r.items);
      })
      .catch((e: Error) => active && setError(e.message));
    return () => {
      active = false;
    };
  }, [session.session_id]);

  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <aside className="drawer" onClick={(e) => e.stopPropagation()}>
        <div className="drawer-head">
          <div>
            <div className="drawer-title">{session.title ?? "Untitled session"}</div>
            <div className="drawer-sub">{session.session_id}</div>
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>

        <div className="drawer-meta">
          <span className="badge" style={{ color: statusColor(session.status) }}>
            {prettyLabel(session.status)}
          </span>
          {session.category && <span className="chip">{prettyLabel(session.category)}</span>}
          {session.origin && <span className="chip">{prettyLabel(session.origin)}</span>}
          <span className="chip">{formatAcus(session.acus_consumed)} ACU</span>
          {session.repo && <span className="chip">{session.repo}</span>}
        </div>

        {session.pull_requests.length > 0 && (
          <div className="drawer-prs">
            {session.pull_requests.map((pr) => (
              <a key={pr.url} href={pr.url} target="_blank" rel="noreferrer" className="pr-link">
                {pr.state ?? "open"} · {pr.url.replace("https://github.com/", "")}
              </a>
            ))}
          </div>
        )}

        <div className="drawer-log">
          <div className="drawer-log-title">Session log</div>
          {error && <div className="error-inline">{error}</div>}
          {!messages && !error && <div className="muted">Loading messages…</div>}
          {messages?.map((m) => (
            <div key={m.event_id} className={`msg msg-${m.source}`}>
              <div className="msg-head">
                <span className="msg-source">{m.source === "user" ? "User" : "Devin"}</span>
                <span className="msg-time">{formatDate(m.created_at)}</span>
              </div>
              <div className="msg-body">{m.message}</div>
            </div>
          ))}
        </div>
      </aside>
    </div>
  );
}
