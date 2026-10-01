import { useState, type ReactNode } from "react";
import { ArrowUp, ChevronRight, Download, GitBranch } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { SessionSummary } from "@/lib/types";
import { formatCost, formatDateTime, formatTokens } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Tooltip, TooltipContent, TooltipTrigger } from "./ui/tooltip";
import { CopyButton } from "./CopyButton";
import { MessageView } from "./MessageView";

const SOURCE_TEXT: Record<string, string> = {
  opencode: "text-opencode",
  gemini: "text-gemini",
  kilocode: "text-kilocode",
  codex: "text-codex",
  claude: "text-claude",
};

export function TranscriptView({
  sessionId,
  onOpenSubagent,
  compact = false,
}: {
  sessionId: string | null;
  onOpenSubagent?: (id: string, title: string) => void;
  /** Denser header for the split pane, where width is scarce. */
  compact?: boolean;
}) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["session", sessionId],
    queryFn: () => api.session(sessionId!),
    enabled: Boolean(sessionId),
  });

  if (!sessionId) {
    return (
      <Notice>
        <div className="text-center">
          <p className="display text-[15px] text-foreground">No session open</p>
          <p className="mt-1 text-[13px]">
            Click a session to preview it, double-click to pin it as a tab.
          </p>
        </div>
      </Notice>
    );
  }
  if (isLoading) return <Notice>Loading transcript…</Notice>;
  if (error || !data) {
    return <Notice tone="error">Failed to load: {String(error)}</Notice>;
  }

  const cost = formatCost(data.usage.cost_usd);

  return (
    <div className="flex h-full flex-col">
      <header
        className={cn(
          "shrink-0 border-b border-border bg-background",
          compact ? "px-4 py-3.5" : "px-8 py-5",
        )}
      >
        <div className="flex items-start gap-5">
          <div className="min-w-0 flex-1">
            <h1
              className={cn(
                "display truncate",
                compact ? "text-sm" : "text-xl",
              )}
            >
              {data.title}
            </h1>

            <div className="mono mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[13px] text-muted-foreground">
              <span className={cn("font-semibold uppercase tracking-wider", SOURCE_TEXT[data.source])}>
                {data.source}
              </span>
              {data.created_at && (
                <>
                  <Dot />
                  <span>{formatDateTime(data.created_at)}</span>
                </>
              )}
              <Dot />
              {/* Human prompts lead: "580 messages" mostly counts the agent
                  talking to itself. Total turns is in the tooltip. */}
              <Tooltip>
                <TooltipTrigger asChild>
                  <span className="cursor-default">
                    {data.user_message_count} prompts
                  </span>
                </TooltipTrigger>
                <TooltipContent>{data.message_count} turns in total</TooltipContent>
              </Tooltip>

              {data.usage.output_tokens > 0 && (
                <>
                <Dot />
                <Tooltip>
                  <TooltipTrigger asChild>
                    <span className="flex cursor-default items-center gap-0.5">
                      <ArrowUp size={12} strokeWidth={2.5} />
                      {formatTokens(data.usage.output_tokens)}
                    </span>
                  </TooltipTrigger>
                  <TooltipContent className="mono">
                    <div>output {data.usage.output_tokens.toLocaleString()}</div>
                    <div>input {data.usage.input_tokens.toLocaleString()}</div>
                    <div>cached {data.usage.cached_tokens.toLocaleString()}</div>
                    <div>thinking {data.usage.thinking_tokens.toLocaleString()}</div>
                  </TooltipContent>
                </Tooltip>
                </>
              )}

              {cost && (
                <>
                  <Dot />
                  <span>{cost}</span>
                </>
              )}
              {data.subagent_count > 0 && (
                <>
                  <Dot />
                  <span className="flex items-center gap-1 text-agent">
                    <GitBranch size={12} strokeWidth={2.5} />
                    {data.subagent_count} subagents
                  </span>
                </>
              )}
            </div>

            {/* cwd and models used to take two full rows; they are reference
                data, not something you read every time. */}
            {(data.cwd || data.models.length > 0) && !compact && (
              <div className="mono mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground/80">
                {data.models.map((model) => (
                  <span key={model} className="text-foreground/60">
                    {model}
                  </span>
                ))}
                {data.cwd && (
                  <>
                    {data.models.length > 0 && <Dot />}
                    <span className="max-w-[36rem] truncate" title={data.cwd}>
                      {data.cwd}
                    </span>
                  </>
                )}
              </div>
            )}
          </div>

          {!compact && (
            <div className="flex shrink-0 items-center gap-1">
              <CopyButton label="Markdown" value={() => api.markdown(data.id)} />
              {/* A plain anchor, not a Button — nesting <a> inside <button> is
                  invalid and breaks the native download behaviour. */}
              <a
                href={`/api/sessions/${encodeURI(data.id)}/markdown`}
                download={`${data.id.replace(/[:/\\]/g, "_")}.md`}
                className={cn(
                  "inline-flex h-7 items-center gap-1.5 rounded-md border border-border",
                  "px-2 text-xs font-medium transition-colors ease-swift hover:bg-accent",
                )}
              >
                <Download size={13} />
                Export
              </a>
            </div>
          )}
        </div>

        {data.fork_count > 0 && (
          <p className="mt-2 text-xs text-muted-foreground">
            {data.fork_count} earlier transcript
            {data.fork_count === 1 ? "" : "s"} of this conversation
            {" "}(resumes/forks) hidden from the list.
          </p>
        )}

        {data.subagents.length > 0 && onOpenSubagent && (
          <SubagentList subagents={data.subagents} onOpen={onOpenSubagent} />
        )}
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {data.messages.map((message, index) => (
          <MessageView
            key={message.id || index}
            message={message}
            messageIndex={index}
            sessionId={data.id}
            continued={
              index > 0 &&
              data.messages[index - 1].role === message.role &&
              message.role !== "user"
            }
            onOpenSubagent={onOpenSubagent}
          />
        ))}
        {data.messages.length === 0 && <Notice>No renderable messages</Notice>}
      </div>
    </div>
  );
}

/** Separator between metadata items, so they read as a list not a run-on. */
function Dot() {
  return <span className="select-none text-muted-foreground/40">·</span>;
}

/**
 * Collapsed by default and capped when open.
 *
 * These were previously rendered as an unbounded grid of buttons. A session
 * with 69 subagent runs pushed the entire transcript below the fold — the
 * header became taller than the viewport. Never render an unbounded collection
 * in a fixed-height region.
 */
function SubagentList({
  subagents,
  onOpen,
}: {
  subagents: SessionSummary[];
  onOpen: (id: string, title: string) => void;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div className="mt-2">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-1.5 text-xs text-muted-foreground transition-colors ease-swift hover:text-foreground"
      >
        <ChevronRight
          size={13}
          className={cn("transition-transform duration-200 ease-swift", open && "rotate-90")}
        />
        <GitBranch size={12} className="text-agent" />
        {subagents.length} subagent {subagents.length === 1 ? "run" : "runs"}
      </button>

      {open && (
        <div className="animate-slide-up-fade mt-2 max-h-56 overflow-y-auto rounded-md border border-border bg-muted/30 p-1">
          {subagents.map((child) => (
            <button
              key={child.id}
              type="button"
              onClick={() => onOpen(child.id, child.title)}
              className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-xs transition-colors ease-swift hover:bg-accent"
            >
              <GitBranch size={11} className="shrink-0 text-agent" />
              <span className="truncate">{child.title}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function Notice({ children, tone }: { children: ReactNode; tone?: "error" }) {
  return (
    <div
      className={cn(
        "flex h-full items-center justify-center p-6 text-[13px]",
        tone === "error" ? "text-destructive" : "text-muted-foreground",
      )}
    >
      {children}
    </div>
  );
}
