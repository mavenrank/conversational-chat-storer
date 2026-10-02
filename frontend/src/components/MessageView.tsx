import { ArrowUp } from "lucide-react";
import { blocksToText, hasScope } from "@/lib/copy";
import { WorkSummary, classify } from "./WorkSummary";
import type { Message } from "@/lib/types";
import {
  formatCost,
  formatDuration,
  formatTime,
  formatTokens,
} from "@/lib/format";
import { cn } from "@/lib/utils";
import { BlockView } from "./BlockView";
import { CopyButton } from "./CopyButton";

/**
 * Distinguishing speakers is done with weight, not decoration:
 *
 *   - User turns get a filled card (`bg-card`), a 4px rail and a "User" label.
 *     They are visually the anchors you scan for.
 *   - Agent turns sit on the page background with no label at all unless they
 *     start a run. An agent working through 40 tool calls should not repeat
 *     "AGENT" 40 times; `continued` suppresses the header and tightens the
 *     padding so a long stretch reads as one block of work.
 */
export function MessageView({
  message,
  messageIndex,
  sessionId,
  continued = false,
  onOpenSubagent,
}: {
  message: Message;
  messageIndex: number;
  sessionId: string;
  /** True when the previous turn had the same role — header is suppressed. */
  continued?: boolean;
  onOpenSubagent?: (id: string, title: string) => void;
}) {
  const isUser = message.role === "user";
  const isError = message.role === "error";
  const usage = message.usage;
  const duration = formatDuration(message.duration_ms);
  const cost = formatCost(usage?.cost_usd ?? null);

  return (
    <article
      className={cn(
        "message group relative",
        isUser
          ? // A distinct surface, not a tint: --user-surface sits several steps
            // off the page background so the turn reads as a card even in
            // peripheral vision.
            "message-user my-4 mx-4 rounded-lg border border-user-border bg-user-surface px-4 py-3.5"
          : cn(
              "message-agent mx-4 border-l-2 pl-4 pr-1",
              isError ? "border-destructive" : "border-border",
            ),
        !isUser && (continued ? "py-1.5" : "pb-3 pt-4"),
      )}
    >
      {isUser && (
        <span className="absolute inset-y-0 left-0 w-1 rounded-l-lg bg-user" />
      )}

      {!continued && (
        <header className="message-header mb-2 flex flex-wrap items-center gap-x-2.5 gap-y-1">
          <span
            className={cn(
              "text-[11px] font-semibold uppercase tracking-wide",
              isUser
                ? "text-user"
                : isError
                  ? "text-destructive"
                  : "text-assistant",
            )}
          >
            {isUser
              ? "User"
              : isError
                ? "Error"
                : message.role === "info"
                  ? "Attachments"
                  : "Agent"}
          </span>

          {message.is_sidechain && (
            <span className="rounded bg-agent/15 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wider text-agent">
              Subagent
            </span>
          )}

          {message.model && !isUser && (
            <span
              className="message-model max-w-[14rem] truncate text-[11px] text-foreground/60"
              title={message.model}
            >
              {message.model}
            </span>
          )}

          <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[11px] tabular-nums text-muted-foreground">
            {message.started_at && (
              <time title={message.started_at}>
                {formatTime(message.started_at)}
              </time>
            )}
            {duration && <span>{duration}</span>}
            {usage && usage.output_tokens > 0 && (
              <span
                className="flex items-center gap-0.5"
                title={[
                  `output    ${usage.output_tokens.toLocaleString()}`,
                  `input     ${usage.input_tokens.toLocaleString()}`,
                  `cached    ${usage.cached_tokens.toLocaleString()}`,
                  `thinking  ${usage.thinking_tokens.toLocaleString()}`,
                ].join("\n")}
              >
                <ArrowUp size={11} strokeWidth={2.5} className="inline" />
                {formatTokens(usage.output_tokens)}
              </span>
            )}
            {cost && <span>{cost}</span>}
          </div>

          {/*
            Three scopes rather than one button. The single button used to copy
            `message.text`, which is prose only — it dropped every tool call and
            every reasoning block, and pasted "undefined" besides.
          */}
          <div className="message-actions ml-auto flex items-center gap-0.5 opacity-60 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100">
            {hasScope(message, "answer") && (
              <CopyButton
                label="Answer"
                title="Copy just the model's prose"
                value={() => blocksToText(message.blocks, "answer")}
              />
            )}
            {hasScope(message, "tools") && (
              <CopyButton
                label="+ tools"
                title="Copy tool calls with their results, then the answer"
                value={() => blocksToText(message.blocks, "tools")}
              />
            )}
            <CopyButton
              label="All"
              title="Copy thinking, tools and answer in order"
              value={() => blocksToText(message.blocks, "full")}
            />
          </div>
        </header>
      )}

      {/*
        Prose stays inline; reasoning and tool calls fold into one "Work" row.
        Block indices are taken before partitioning, because a block's ref is
        its position in the original array — renumbering would make the lazy
        fetch load the wrong block.
      */}
      <div className="space-y-2">
        {(() => {
          const indexed = message.blocks.map((block, i) => ({ block, i }));
          const work = indexed.filter(({ block }) => classify(block) !== null);
          const prose = indexed.filter(({ block }) => classify(block) === null);

          return (
            <>
              {work.length > 0 && (
                <WorkSummary blocks={work.map((w) => w.block)}>
                  {work.map(({ block, i }) => (
                    <BlockView
                      key={i}
                      block={block}
                      sessionId={sessionId}
                      blockRef={`${messageIndex}.${i}`}
                      onOpenSubagent={onOpenSubagent}
                    />
                  ))}
                </WorkSummary>
              )}
              {prose.map(({ block, i }) => (
                <BlockView
                  key={i}
                  block={block}
                  sessionId={sessionId}
                  blockRef={`${messageIndex}.${i}`}
                  onOpenSubagent={onOpenSubagent}
                />
              ))}
            </>
          );
        })()}
      </div>
    </article>
  );
}
