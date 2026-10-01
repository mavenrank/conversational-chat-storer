import { useState, type ReactNode } from "react";
import {
  Brain,
  FileDiff,
  FilePlus,
  FileText,
  GitBranch,
  Search,
  Terminal,
  Wrench,
} from "lucide-react";
import type { Block, ToolDetail } from "@/lib/types";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { toolToText } from "@/lib/copy";
import { Accordion, type Tone } from "./Accordion";
import { Button } from "./ui/button";
import { CopyButton } from "./CopyButton";
import { Diff } from "./Diff";
import { Markdown } from "./Markdown";

interface BlockViewProps {
  block: Block;
  sessionId: string;
  /** `<messageIndex>.<blockIndex>` — the address used to fetch elided content. */
  blockRef: string;
  /** Opens a subagent transcript in the split pane. */
  onOpenSubagent?: (id: string, title: string) => void;
}

export function BlockView({ block, sessionId, blockRef, onOpenSubagent }: BlockViewProps) {
  if (block.kind === "text") {
    return (
      <div className="group/text relative py-1.5 pl-4 pr-8">
        <div className="prose-body">
          <Markdown text={block.text} />
        </div>
        <CopyButton
          value={block.text}
          className="absolute right-0 top-0 opacity-0 transition-opacity group-hover/text:opacity-100"
        />
      </div>
    );
  }

  if (block.kind === "thinking") {
    return <ThinkingView block={block} sessionId={sessionId} blockRef={blockRef} />;
  }

  return (
    <ToolView
      block={block}
      sessionId={sessionId}
      blockRef={blockRef}
      onOpenSubagent={onOpenSubagent}
    />
  );
}

/** Fetches a block's full payload on first expand; inline content short-circuits. */
function useLazyBlock(sessionId: string, blockRef: string, elided: boolean) {
  const [loaded, setLoaded] = useState<Block | null>(null);
  const [loading, setLoading] = useState(false);

  async function load() {
    if (!elided || loaded || loading) return;
    setLoading(true);
    try {
      setLoaded(await api.block(sessionId, blockRef));
    } finally {
      setLoading(false);
    }
  }

  return { loaded, loading, load };
}

function ThinkingView({
  block,
  sessionId,
  blockRef,
}: {
  block: Extract<Block, { kind: "thinking" }>;
  sessionId: string;
  blockRef: string;
}) {
  const { loaded, loading, load } = useLazyBlock(sessionId, blockRef, block.elided);
  const resolved = loaded?.kind === "thinking" ? loaded : null;
  const text = resolved?.text || block.text;

  return (
    <Accordion
      tone="think"
      icon={<Glyph className="text-muted-foreground"><Brain size={13} /></Glyph>}
      label={
        <span className="italic text-muted-foreground">{block.subject || "thinking"}</span>
      }
      sizeBytes={block.size_bytes}
      onFirstOpen={load}
      meta={
        text ? (
          <CopyButton
            value={text}
            title="Copy this reasoning"
            className="opacity-0 transition-opacity group-hover/row:opacity-100"
          />
        ) : undefined
      }
    >
      <div className="px-4 py-3">
        {loading ? (
          <Loading />
        ) : text ? (
          <div className="whitespace-pre-wrap text-[13px] leading-[1.75] text-foreground/75">
            {text}
          </div>
        ) : (
          <div className="text-xs text-muted-foreground">No reasoning text recorded.</div>
        )}
      </div>
    </Accordion>
  );
}

function ToolView({
  block,
  sessionId,
  blockRef,
  onOpenSubagent,
}: {
  block: Extract<Block, { kind: "tool_use" }>;
  sessionId: string;
  blockRef: string;
  onOpenSubagent?: (id: string, title: string) => void;
}) {
  const elided = "elided" in block.detail ? block.detail.elided : false;
  const { loaded, loading, load } = useLazyBlock(sessionId, blockRef, elided);
  const detail = loaded?.kind === "tool_use" ? loaded.detail : block.detail;
  const { tone, icon, label } = describe(block.name, detail);

  return (
    <Accordion
      tone={tone}
      error={block.status === "error"}
      icon={icon}
      label={label}
      meta={
        <>
          {block.status === "error" && (
            <span className="shrink-0 text-xs text-destructive">error</span>
          )}
          {/* Copies the query and its result as one unit — previously the two
              had separate buttons and no way to take both. */}
          <CopyButton
            value={() => toolToText({ ...block, detail })}
            title="Copy this call and its result"
            className="opacity-0 transition-opacity group-hover/row:opacity-100"
          />
        </>
      }
      sizeBytes={"size_bytes" in block.detail ? block.detail.size_bytes : undefined}
      onFirstOpen={load}
    >
      {loading ? (
        <Loading />
      ) : (
        <>
          {block.error && (
            <div className="border-b border-border px-4 py-2 text-xs text-destructive">
              {block.error}
            </div>
          )}
          <Body detail={detail} onOpenSubagent={onOpenSubagent} />
        </>
      )}
    </Accordion>
  );
}

/** Wraps a lucide icon so every row's leading glyph aligns identically. */
function Glyph({ children, className }: { children: ReactNode; className?: string }) {
  return <span className={cn("flex shrink-0 items-center", className)}>{children}</span>;
}

function Path({ value, color }: { value: string; color: string }) {
  const parts = value.split(/[\\/]/);
  const file = parts.pop() ?? value;
  const dir = parts.join("/");
  return (
    <span className="text-[13px]">
      {dir && <span className="text-muted-foreground">{shortenDir(dir)}/</span>}
      <span className={color}>{file}</span>
    </span>
  );
}

/** Keep the tail of long absolute paths — the leading directories are noise. */
function shortenDir(dir: string, max = 34): string {
  if (dir.length <= max) return dir;
  return `…${dir.slice(-max)}`;
}

function describe(
  name: string,
  detail: ToolDetail,
): { tone: Tone; icon: ReactNode; label: ReactNode } {
  switch (detail.category) {
    case "file_read":
      return {
        tone: "read",
        icon: <Glyph className="text-read"><FileText size={13} /></Glyph>,
        label: (
          <>
            <Verb className="text-read">read</Verb>
            <Path value={detail.path} color="text-foreground/75" />
          </>
        ),
      };
    case "file_write":
      return {
        tone: "write",
        icon: <Glyph className="text-write"><FilePlus size={13} /></Glyph>,
        label: (
          <>
            <Verb className="text-write">write</Verb>
            <Path value={detail.path} color="text-foreground" />
          </>
        ),
      };
    case "file_edit":
      return {
        tone: "edit",
        icon: <Glyph className="text-edit"><FileDiff size={13} /></Glyph>,
        label: (
          <>
            <Verb className="text-edit">edit</Verb>
            <Path value={detail.path} color="text-foreground" />
            {(detail.additions > 0 || detail.deletions > 0) && (
              <span className="ml-2 text-xs tabular-nums">
                <span className="text-add">+{detail.additions}</span>
                <span className="text-muted-foreground">/</span>
                <span className="text-destructive">−{detail.deletions}</span>
              </span>
            )}
          </>
        ),
      };
    case "command":
      return {
        tone: "command",
        icon: <Glyph className="text-command"><Terminal size={13} /></Glyph>,
        label: (
          <span className="text-[13px] text-foreground/80">
            {truncate(detail.command.replace(/\s+/g, " "), 120)}
          </span>
        ),
      };
    case "search":
      return {
        tone: "search",
        icon: <Glyph className="text-search"><Search size={13} /></Glyph>,
        label: (
          <>
            <Verb className="text-search">{name}</Verb>
            <span className="text-[13px] text-foreground/80">
              {truncate(detail.query, 90)}
            </span>
          </>
        ),
      };
    case "subagent":
      return {
        tone: "agent",
        icon: <Glyph className="text-agent"><GitBranch size={13} /></Glyph>,
        label: (
          <>
            <span className="mr-2 rounded-sm bg-agent/15 px-1.5 py-[1px] text-xs text-agent">
              {detail.agent_type || "subagent"}
            </span>
            <span className="text-[13px] text-foreground/80">{detail.description}</span>
          </>
        ),
      };
    default:
      return {
        tone: "plain",
        icon: <Glyph className="text-muted-foreground"><Wrench size={13} /></Glyph>,
        label: <span className="text-[13px] text-muted-foreground">{name}</span>,
      };
  }
}

function Verb({ children, className }: { children: ReactNode; className: string }) {
  return <span className={cn("mr-2 text-[13px]", className)}>{children}</span>;
}

function Body({
  detail,
  onOpenSubagent,
}: {
  detail: ToolDetail;
  onOpenSubagent?: (id: string, title: string) => void;
}) {
  switch (detail.category) {
    case "file_edit":
      return (
        <Diff
          unified={detail.unified_diff}
          oldText={detail.old_text}
          newText={detail.new_text}
        />
      );
    case "file_read":
    case "file_write":
      return <Code text={detail.content} />;
    case "command":
      return (
        <div>
          <div className="border-b border-border px-4 py-2.5 text-[13px] text-command">
            <span className="mr-1.5 text-muted-foreground">$</span>
            {detail.command}
          </div>
          <Code text={detail.output} />
        </div>
      );
    case "search":
      return <Code text={detail.output} />;
    case "subagent":
      return (
        <div className="space-y-4 px-4 py-3.5">
          {detail.prompt && (
            <Field label="prompt">
              <div className="max-h-56 overflow-auto whitespace-pre-wrap rounded-sm bg-background/60 p-2 text-xs text-foreground/75">
                {detail.prompt}
              </div>
            </Field>
          )}
          {detail.result && (
            <Field label="result">
              <div className="prose-body">
                <Markdown text={detail.result} />
              </div>
            </Field>
          )}
          {detail.child_session_id && onOpenSubagent && (
            <Button
              variant="outline"
              size="sm"
              onClick={() =>
                onOpenSubagent(
                  detail.child_session_id!,
                  detail.description || detail.agent_type || "Subagent",
                )
              }
            >
              <GitBranch size={13} className="text-agent" />
              Open full transcript in split pane
            </Button>
          )}
        </div>
      );
    default:
      return (
        <div>
          {Object.keys(detail.input ?? {}).length > 0 && (
            <Code text={JSON.stringify(detail.input, null, 2)} />
          )}
          {detail.output && <Code text={detail.output} />}
        </div>
      );
  }
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
        {label}
      </div>
      {children}
    </div>
  );
}

function Code({ text }: { text: string }) {
  if (!text) {
    return <div className="px-4 py-2.5 text-xs text-muted-foreground">no output</div>;
  }
  return (
    <div className="group/code relative">
      <pre className="max-h-[30rem] overflow-auto whitespace-pre px-4 py-3 text-[12.5px] leading-[1.7] text-foreground/75">
        {text}
      </pre>
      <CopyButton
        value={text}
        className="absolute right-1 top-1 bg-card opacity-0 transition-opacity group-hover/code:opacity-100"
      />
    </div>
  );
}

function Loading() {
  return (
    <div className="px-4 py-2.5 text-xs text-muted-foreground">
      <span className="animate-pulse">loading…</span>
    </div>
  );
}

function truncate(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max)}…` : text;
}
