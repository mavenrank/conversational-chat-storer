/**
 * Mirrors the backend's pydantic models. Kept hand-written rather than
 * generated so the shapes stay readable; they are small and change rarely.
 */

export type SourceId = "claude" | "gemini" | "opencode" | "kilocode" | "codex";

export type Role = "user" | "assistant" | "system" | "info" | "error";

export type ToolStatus = "pending" | "running" | "completed" | "error";

/** Fields present on every payload that can be elided for lazy loading. */
export interface HeavyMeta {
  elided: boolean;
  size_bytes: number;
}

export type ToolDetail =
  | ({ category: "file_read"; path: string; content: string; truncated: boolean } & HeavyMeta)
  | ({ category: "file_write"; path: string; content: string } & HeavyMeta)
  | ({
      category: "file_edit";
      path: string;
      old_text: string;
      new_text: string;
      unified_diff: string;
      additions: number;
      deletions: number;
    } & HeavyMeta)
  | ({ category: "command"; command: string; output: string; exit_code: number | null } & HeavyMeta)
  | ({ category: "search"; query: string; output: string } & HeavyMeta)
  | ({
      category: "subagent";
      agent_type: string;
      description: string;
      prompt: string;
      result: string;
      child_session_id: string | null;
    } & HeavyMeta)
  | ({ category: "generic"; input: Record<string, unknown>; output: string } & HeavyMeta);

export type Block =
  | { kind: "text"; text: string }
  | { kind: "thinking"; text: string; subject: string | null; elided: boolean; size_bytes: number }
  | {
      kind: "tool_use";
      tool_id: string | null;
      name: string;
      status: ToolStatus;
      error: string | null;
      duration_ms: number | null;
      detail: ToolDetail;
    };

export interface Usage {
  input_tokens: number;
  output_tokens: number;
  cached_tokens: number;
  thinking_tokens: number;
  tool_tokens: number;
  cost_usd: number | null;
  total_tokens: number;
}

export interface Message {
  id: string;
  role: Role;
  blocks: Block[];
  started_at: string | null;
  completed_at: string | null;
  model: string | null;
  provider: string | null;
  usage: Usage | null;
  is_sidechain: boolean;
  duration_ms: number | null;
  text: string;
}

export interface ProjectRef {
  id: string;
  name: string;
  path: string;
}

export interface SessionSummary {
  id: string;
  source: SourceId;
  title: string;
  project: ProjectRef | null;
  cwd: string;
  created_at: string | null;
  updated_at: string | null;
  message_count: number;
  /** Turns the human actually typed — what the UI leads with. */
  user_message_count: number;
  models: string[];
  usage: Usage;
  is_subagent: boolean;
  parent_session_id: string | null;
  subagent_count: number;
  is_fork: boolean;
  fork_of: string | null;
  fork_count: number;
  source_path: string;
}

export interface SessionDetail extends SessionSummary {
  messages: Message[];
  subagents: SessionSummary[];
  forks: SessionSummary[];
}

export interface SourceStatus {
  id: SourceId;
  display_name: string;
  available: boolean;
  root: string;
  session_count: number;
  error: string | null;
}

export interface SearchHit {
  session: SessionSummary;
  field: "title" | "message";
  excerpt: string;
}

export interface Stats {
  session_count: number;
  message_count: number;
  /**
   * Reported as a breakdown, not one sum. Agent loops resend the whole
   * conversation each request, so summed `input` (and cache reads) counts the
   * same context many times over. `output_tokens` is the only figure that
   * reflects text actually generated, so the UI leads with it.
   */
  input_tokens: number;
  output_tokens: number;
  cached_tokens: number;
  thinking_tokens: number;
  cumulative_tokens: number;
  total_cost_usd: number;
  by_source: Record<string, number>;
  by_model: Record<string, number>;
}


export interface ArchiveStats {
  session_count: number;
  by_source: Record<string, number>;
  root: string;
  size_bytes: number;
}

export interface ArchiveResult {
  added: number;
  updated: number;
  unchanged: number;
  failed: number;
  errors: string[];
}
