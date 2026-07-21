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
