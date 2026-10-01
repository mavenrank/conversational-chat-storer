import { useMemo, useState, type ReactNode } from "react";
import { ArrowUp, GitBranch, Search, X } from "lucide-react";
import type { SessionSummary } from "@/lib/types";
import { formatRelative, formatTokens } from "@/lib/format";
import { cn } from "@/lib/utils";

const SOURCE_DOT: Record<string, string> = {
  opencode: "bg-opencode",
  gemini: "bg-gemini",
  kilocode: "bg-kilocode",
  codex: "bg-codex",
  claude: "bg-claude",
};

export function SessionList({
  sessions,
  activeId,
  openIds,
  loading,
  onOpen,
  onPin,
}: {
  sessions: SessionSummary[];
  activeId: string | null;
  openIds: string[];
  loading: boolean;
  onOpen: (session: SessionSummary) => void;
  onPin: (session: SessionSummary) => void;
}) {
  const [filter, setFilter] = useState("");
  const open = useMemo(() => new Set(openIds), [openIds]);

  const visible = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    if (!needle) return sessions;
    return sessions.filter(
      (s) =>
        s.title.toLowerCase().includes(needle) ||
        s.cwd.toLowerCase().includes(needle) ||
        s.models.some((m) => m.toLowerCase().includes(needle)),
    );
  }, [sessions, filter]);

  return (
    <div className="flex h-full flex-col border-r border-border bg-muted/25">
      <div className="shrink-0 p-3">
        <div className="flex items-center gap-2.5 rounded-md border border-input bg-background px-3 py-2.5 transition-colors ease-swift focus-within:border-ring">
          <Search size={14} className="shrink-0 text-muted-foreground" />
          <input
            value={filter}
            onChange={(event) => setFilter(event.target.value)}
            placeholder="Filter sessions"
            className="w-full bg-transparent text-[13px] placeholder:text-muted-foreground focus:outline-none"
          />
          {filter && (
            <button
              type="button"
              onClick={() => setFilter("")}
              className="text-muted-foreground transition-colors ease-swift hover:text-foreground"
            >
              <X size={13} />
            </button>
          )}
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {loading && <Empty>Loading sessions…</Empty>}
        {!loading && visible.length === 0 && <Empty>No sessions</Empty>}

        {visible.map((session) => {
          const active = activeId === session.id;
          return (
            <button
              key={session.id}
              type="button"
              onClick={() => onOpen(session)}
              onDoubleClick={() => onPin(session)}
              className={cn(
                "relative block w-full border-b border-border/40 px-3 py-3 text-left",
                "transition-colors ease-swift",
                active ? "bg-background" : "hover:bg-background/60",
              )}
            >
              {active && (
                <span className="absolute inset-y-0 left-0 w-[3px] bg-primary" />
              )}

              {/*
                Two lines, not four. The source is a 3px colour bar rather than
                a text label — the colour already identifies the tool, so the
                word was pure duplication. Everything else collapses onto one
                metadata line with the full detail in its tooltip.
              */}
              <div className="flex items-start gap-2.5">
                <span
                  className={cn(
                    "mt-1 h-3.5 w-[3px] shrink-0 rounded-full",
                    SOURCE_DOT[session.source] ?? "bg-muted-foreground",
                  )}
                  title={session.source}
                />
                <span
                  className={cn(
                    "line-clamp-2 flex-1 text-sm leading-snug",
                    active ? "font-semibold text-foreground" : "text-foreground/85",
                  )}
                >
                  {session.title}
                </span>
                {open.has(session.id) && !active && (
                  <span
                    className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-muted-foreground"
                    title="Open in a tab"
                  />
                )}
              </div>

              <div className="mono mt-1.5 flex items-center gap-2 pl-[22px] text-[11px] text-muted-foreground">
                <span className="shrink-0">
                  {formatRelative(session.updated_at ?? session.created_at)}
                </span>
                {session.user_message_count > 0 && (
                  <span
                    className="shrink-0"
                    title={`${session.message_count} turns in total`}
                  >
                    · {session.user_message_count}p
                  </span>
                )}
                {session.usage.output_tokens > 0 && (
                  <span
                    className="flex shrink-0 items-center gap-0.5"
                    title="Tokens generated"
                  >
                    · <ArrowUp size={10} strokeWidth={2.5} />
                    {formatTokens(session.usage.output_tokens)}
                  </span>
                )}
                {session.subagent_count > 0 && (
                  <span
                    className="flex shrink-0 items-center gap-0.5 text-agent"
                    title="Subagent runs"
                  >
                    · <GitBranch size={10} strokeWidth={2.5} />
                    {session.subagent_count}
                  </span>
                )}
                {session.project?.name && (
                  <span className="truncate opacity-60" title={session.cwd}>
                    · {session.project.name}
                  </span>
                )}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function Empty({ children }: { children: ReactNode }) {
  return <div className="p-6 text-[13px] text-muted-foreground">{children}</div>;
}
