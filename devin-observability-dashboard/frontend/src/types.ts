export interface PullRequest {
  url: string;
  state: string | null;
}

export interface Session {
  session_id: string;
  title: string | null;
  status: string;
  created_at: number;
  updated_at: number;
  acus_consumed: number;
  org_id: string | null;
  user_id: string | null;
  user_name: string | null;
  origin: string | null;
  category: string | null;
  repo: string | null;
  tags: string[];
  pull_requests: PullRequest[];
}

export interface Kpis {
  total_sessions: number;
  total_acus: number;
  prs_created: number;
  prs_merged: number;
  pr_merge_rate: number;
  success_rate: number;
  active_users: number;
  acus_per_merged_pr: number;
  avg_acus_per_session: number;
}

export interface TimePoint {
  date: string;
  sessions: number;
  prs_merged: number;
  acus: number;
  acus_devin: number;
  acus_cascade: number;
  acus_terminal: number;
  acus_review: number;
}

export interface NamedCount {
  name: string;
  count: number;
  acus: number;
}

export interface Overview {
  generated_at: number;
  is_demo: boolean;
  range_days: number;
  kpis: Kpis;
  timeseries: TimePoint[];
  by_status: NamedCount[];
  by_category: NamedCount[];
  by_origin: NamedCount[];
  by_repo: NamedCount[];
  by_user: NamedCount[];
  by_org: NamedCount[];
  recent_sessions: Session[];
}

export interface Message {
  event_id: string;
  source: string;
  message: string;
  created_at: number;
}

export interface MessagesResponse {
  session_id: string;
  is_demo: boolean;
  items: Message[];
}

export interface AutomationRecord {
  issue_number: number;
  title: string | null;
  category: string | null;
  status: string;
  session_id: string | null;
  session_url: string | null;
  pr_url: string | null;
  created_at: number | null;
  updated_at: number | null;
}

export interface AutomationSummary {
  total_triggered: number;
  in_progress: number;
  finished: number;
  prs_opened: number;
  blocked_or_failed: number;
  success_rate_pct: number | null;
  avg_time_to_finish_sec: number | null;
}

export interface AutomationStatus {
  enabled: boolean;
  is_demo: boolean;
  repo: string;
  trigger_label: string;
  generated_at: number;
  summary: AutomationSummary;
  records: AutomationRecord[];
}
