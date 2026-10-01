/** Typed API client. One function per endpoint, no client-side caching here — that is TanStack Query's job. */

import type {
  ArchiveResult,
  ArchiveStats,
  Block,
  SearchHit,
  SessionDetail,
  SessionSummary,
  SourceStatus,
  Stats,
  CostStats,
} from "./types";

async function get<T>(path: string): Promise<T> {
  const response = await fetch(path, { headers: { Accept: "application/json" } });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText} — ${path}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  sources: () => get<SourceStatus[]>("/api/sources"),

  sessions: async (params: { sources?: string[]; includeSubagents?: boolean } = {}) => {
    const query = new URLSearchParams();
    params.sources?.forEach((s) => query.append("source", s));
    if (params.includeSubagents) query.set("include_subagents", "true");
    // The server's default page holds only 200 chats. Keep fetching rather
    // than silently dropping older history from the sidebar and its search.
    const pageSize = 1000;
    query.set("limit", String(pageSize));
    const sessions = new Map<string, SessionSummary>();
    for (let offset = 0; ; offset += pageSize) {
      query.set("offset", String(offset));
      const page = await get<SessionSummary[]>(`/api/sessions?${query}`);
      page.forEach((session) => sessions.set(session.id, session));
      if (page.length < pageSize) return [...sessions.values()];
    }
  },

  session: (id: string) => get<SessionDetail>(`/api/sessions/${encodeURI(id)}`),

  /** Full payload for one elided block, addressed as `<messageIndex>.<blockIndex>`. */
  block: (sessionId: string, ref: string) =>
    get<Block>(`/api/sessions/${encodeURI(sessionId)}/blocks/${ref}`),

  markdown: async (id: string) => {
    const response = await fetch(`/api/sessions/${encodeURI(id)}/markdown`);
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    return response.text();
  },

  search: (query: string) =>
    get<SearchHit[]>(`/api/search?q=${encodeURIComponent(query)}`),

  stats: () => get<Stats>("/api/stats"),
  costs: () => get<CostStats>("/api/costs"),

  archive: {
    stats: () => get<ArchiveStats>("/api/archive"),
    sessions: () => get<SessionSummary[]>("/api/archive/sessions"),
    run: async () => {
      const response = await fetch("/api/archive/run", { method: "POST" });
      if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
      return (await response.json()) as ArchiveResult;
    },
  },
};
