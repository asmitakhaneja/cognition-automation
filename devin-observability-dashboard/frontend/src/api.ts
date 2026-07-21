import type { MessagesResponse, Overview } from "./types";

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Request failed (${res.status}): ${detail}`);
  }
  return (await res.json()) as T;
}

export function fetchOverview(days: number): Promise<Overview> {
  return getJson<Overview>(`/api/overview?days=${days}`);
}

export function fetchMessages(sessionId: string): Promise<MessagesResponse> {
  return getJson<MessagesResponse>(
    `/api/sessions/${encodeURIComponent(sessionId)}/messages`,
  );
}
