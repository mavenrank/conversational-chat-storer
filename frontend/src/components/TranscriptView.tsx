import { useState, type ReactNode } from "react";
import { ArrowUp, ChevronRight, Download, GitBranch } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { SessionSummary } from "@/lib/types";
import { SOURCE_STYLE } from "@/lib/sources";
import { formatCost, formatDateTime, formatTokens } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Tooltip, TooltipContent, TooltipTrigger } from "./ui/tooltip";
import { SourceIcon } from "./SourceIcon";
import { CopyButton } from "./CopyButton";
import { MessageView } from "./MessageView";

export function TranscriptView({
  sessionId,
  onOpenSubagent,
  compact = false,
}: {
  sessionId: string | null;
  onOpenSubagent?: (id: string, title: string) => void;
  compact?: boolean;
}) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["session", sessionId],
    queryFn: () => api.session(sessionId!),
    enabled: Boolean(sessionId),
    staleTime: 5000,
    refetchInterval: 10_000,
  });
  if (!sessionId)
    return (
      <Notice>
        <div className="max-w-xs text-center">
          <p className="text-sm font-medium text-foreground">
            Choose a chat from history
          </p>
          <p className="mt-2 text-[13px] leading-relaxed">
            Click to preview. Double-click to keep it open in a tab.
          </p>
        </div>
      </Notice>
    );
  if (isLoading) return <Notice>Loading transcript…</Notice>;
  if (error || !data)
    return <Notice tone="error">Failed to load: {String(error)}</Notice>;

  const cost = formatCost(data.usage.cost_usd);
  const estimate = data.cost_estimate;
  const source = SOURCE_STYLE[data.source];
  return (
    <section
      className="transcript flex h-full min-w-0 flex-col"
      aria-label={data.title}
    >
      <header className="transcript-header max-h-[50%] shrink-0 overflow-y-auto border-b border-border bg-background px-4 py-3">
        <div className="flex items-start gap-3">
          <h1 className="min-w-0 flex-1 break-words text-[16px] font-semibold leading-snug tracking-tight">
            {data.title}
          </h1>
          {!compact && (
            <div className="flex shrink-0 items-center gap-1">
              <CopyButton
                title="Copy chat as Markdown"
                value={() => api.markdown(data.id)}
                className="h-7 w-7 justify-center p-0"
              />
              <a
                href={`/api/sessions/${encodeURI(data.id)}/markdown`}
                download={`${data.id.replace(/[:/\\]/g, "_")}.md`}
                aria-label="Export chat as Markdown"
                title="Export chat as Markdown"
                className="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <Download size={15} />
              </a>
            </div>
          )}
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs text-muted-foreground">
          <span
            className={cn(
              "inline-flex items-center gap-1.5 rounded-md px-2 py-1 font-medium",
              source.background,
              source.text,
            )}
          >
            <SourceIcon source={data.source} className="h-3.5 w-3.5" />
            {source.label}
          </span>
          <Tooltip>
            <TooltipTrigger asChild>
              <span className="cursor-default whitespace-nowrap tabular-nums">
                {data.user_message_count} prompts
              </span>
            </TooltipTrigger>
            <TooltipContent>{data.message_count} turns in total</TooltipContent>
          </Tooltip>
          {data.usage.output_tokens > 0 && (
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="flex cursor-default items-center gap-1 whitespace-nowrap tabular-nums">
                  <ArrowUp size={12} />
                  {formatTokens(data.usage.output_tokens)}
                </span>
              </TooltipTrigger>
              <TooltipContent>
                <div>Output {data.usage.output_tokens.toLocaleString()}</div>
                <div>Input {data.usage.input_tokens.toLocaleString()}</div>
                <div>Cached {data.usage.cached_tokens.toLocaleString()}</div>
                <div>
                  Thinking {data.usage.thinking_tokens.toLocaleString()}
                </div>
              </TooltipContent>
            </Tooltip>
          )}
          {cost ? (
            <span className="tabular-nums" title="Cost recorded by the source">
              Recorded {cost}
            </span>
          ) : estimate?.estimated_usd != null ? (
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="cursor-default tabular-nums">
                  ≈ {formatCost(estimate.estimated_usd)}
                  {!estimate.complete && " · partial"}
                </span>
              </TooltipTrigger>
              <TooltipContent className="max-w-xs">
                Current standard API estimate · rates checked{" "}
                {estimate.rates_verified_at}. This is not a subscription charge.
                {estimate.unpriced_requests > 0 &&
                  ` ${estimate.unpriced_requests} requests could not be priced.`}
                {estimate.missing_usage_tokens > 0 &&
                  " Some token usage is missing or could not be priced."}
                {estimate.is_stale && " New activity is waiting to be priced."}
                {estimate.calculated_at &&
                  ` Calculated ${formatDateTime(estimate.calculated_at)}.`}
              </TooltipContent>
            </Tooltip>
          ) : (
            <span
              className="text-[11px]"
              title={
                estimate
                  ? "No verified rate or usable request usage was found"
                  : "Cost estimates are calculated in the background"
              }
            >
              {estimate ? "Cost unavailable" : "Cost pending"}
            </span>
          )}
          {data.is_archived && (
            <span className="rounded border border-border px-1.5 py-0.5">
              Archived
            </span>
          )}
        </div>
        {data.updated_at && (
          <p
            className="mt-2 text-[11px] leading-relaxed text-muted-foreground"
            title="Last activity"
          >
            Last active {formatDateTime(data.updated_at)}
          </p>
        )}
        <details className="mt-1.5 text-xs text-muted-foreground">
          <summary className="inline-flex cursor-pointer list-none items-center gap-1 rounded py-0.5 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
            Chat details <ChevronRight size={12} className="details-chevron" />
          </summary>
          <div className="space-y-1.5 pb-1 pt-2 text-[11px] leading-relaxed">
            {data.created_at && (
              <p>Created {formatDateTime(data.created_at)}</p>
            )}
            {(data.usage.cache_write_tokens > 0 ||
              data.usage.cache_write_1h_tokens > 0) && (
              <p>
                Cache writes:{" "}
                {(
                  data.usage.cache_write_tokens +
                  data.usage.cache_write_1h_tokens
                ).toLocaleString()}{" "}
                tokens
              </p>
            )}
            {data.models.length > 0 && (
              <p className="break-words">Models: {data.models.join(", ")}</p>
            )}
            {data.cwd && <p className="break-all">Workspace: {data.cwd}</p>}
            {data.fork_count > 0 && (
              <p>
                {data.fork_count} earlier transcript
                {data.fork_count === 1 ? "" : "s"} of this conversation.
              </p>
            )}
          </div>
        </details>
        {data.subagents.length > 0 && onOpenSubagent && (
          <SubagentList subagents={data.subagents} onOpen={onOpenSubagent} />
        )}
      </header>
      <div className="transcript-messages min-h-0 min-w-0 flex-1 overflow-y-auto overflow-x-hidden">
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
    </section>
  );
}

function SubagentList({
  subagents,
  onOpen,
}: {
  subagents: SessionSummary[];
  onOpen: (id: string, title: string) => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-1.5">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="inline-flex items-center gap-1.5 rounded py-1 text-xs text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <ChevronRight
          size={12}
          className={cn("transition-transform", open && "rotate-90")}
        />
        <GitBranch size={12} className="text-agent" />
        {subagents.length} agent runs
      </button>
      {open && (
        <div className="mt-1 grid max-h-28 gap-1 overflow-y-auto rounded-md border border-border bg-muted/20 p-1.5">
          {subagents.map((s) => (
            <button
              key={s.id}
              type="button"
              onClick={() => onOpen(s.id, s.title)}
              className="flex items-center gap-2 rounded px-2 py-1.5 text-left text-xs hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <GitBranch size={12} className="shrink-0 text-agent" />
              <span className="truncate">{s.title}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function Notice({
  children,
  tone = "normal",
}: {
  children: ReactNode;
  tone?: "normal" | "error";
}) {
  return (
    <div
      className={cn(
        "flex h-full items-center justify-center p-5 text-[13px]",
        tone === "error" ? "text-destructive" : "text-muted-foreground",
      )}
    >
      {children}
    </div>
  );
}
