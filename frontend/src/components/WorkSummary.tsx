import { useState } from "react";
import { Brain, ChevronRight, Hammer, Search } from "lucide-react";
import type { Block } from "@/lib/types";
import { cn } from "@/lib/utils";
import { blocksToText } from "@/lib/copy";
import { CopyButton } from "./CopyButton";

/**
 * One collapsible wrapper around everything the agent *did*, so a turn reads as
 * "here is the answer" with the working folded away behind a single row.
 *
 * The header counts three kinds separately rather than as one total, because
 * they answer different questions while skimming: how much did it reason, how
 * much did it look things up, how much did it touch.
 */
export type WorkKind = "thinking" | "search" | "tool";

/** Tools that reach outside the machine for information. */
const SEARCH_TOOLS = new Set([
  "tinysearch",
  "websearch",
  "web_search",
  "webfetch",
  "web_fetch",
  "google_web_search",
  "search",
  "fetch",
]);

/**
 * Classify a block. Search is split out by *tool name* rather than by detail
 * category, because `SearchDetail` also covers glob and grep — local file
 * searching, which is work on the machine rather than a lookup out of it.
 */
export function classify(block: Block): WorkKind | null {
  if (block.kind === "thinking") return "thinking";
  if (block.kind !== "tool_use") return null;

  const name = block.name.toLowerCase();
  if (SEARCH_TOOLS.has(name)) return "search";
  // Catch `mcp__tinysearch__query` and similar namespaced names.
  if (/(^|_)(tinysearch|websearch|webfetch)(_|$)/.test(name)) return "search";
  return "tool";
}

export function countWork(blocks: Block[]): Record<WorkKind, number> {
  const counts: Record<WorkKind, number> = { thinking: 0, search: 0, tool: 0 };
  for (const block of blocks) {
    const kind = classify(block);
    if (kind) counts[kind] += 1;
  }
  return counts;
}

export function WorkSummary({
  blocks,
  children,
  defaultOpen = false,
}: {
  blocks: Block[];
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const counts = countWork(blocks);
  const total = counts.thinking + counts.search + counts.tool;
  if (total === 0) return null;

  return (
    <div className="overflow-hidden rounded-lg border border-border/70 bg-muted/20">
      <div className="group/work flex items-center gap-2 pr-2">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="flex flex-1 items-center gap-2.5 px-3 py-2 text-left transition-colors ease-swift hover:bg-accent/40"
        >
          <ChevronRight
            size={14}
            strokeWidth={2.5}
            className={cn(
              "shrink-0 text-muted-foreground transition-transform duration-200 ease-swift",
              open && "rotate-90",
            )}
          />
          <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Work
          </span>

          <span className="flex items-center gap-3 text-xs tabular-nums text-muted-foreground">
            {counts.thinking > 0 && (
              <Count
                icon={<Brain size={13} className="text-assistant" />}
                value={counts.thinking}
                label={`${counts.thinking} reasoning block${counts.thinking === 1 ? "" : "s"}`}
              />
            )}
            {counts.search > 0 && (
              <Count
                icon={<Search size={13} className="text-search" />}
                value={counts.search}
                label={`${counts.search} search${counts.search === 1 ? "" : "es"} or fetches`}
              />
            )}
            {counts.tool > 0 && (
              <Count
                icon={<Hammer size={13} className="text-edit" />}
                value={counts.tool}
                label={`${counts.tool} other tool call${counts.tool === 1 ? "" : "s"}`}
              />
            )}
          </span>

          <span className="ml-auto text-xs text-muted-foreground">
            {open ? "hide" : "show"}
          </span>
        </button>

        <CopyButton
          value={() => blocksToText(blocks, "full")}
          title="Copy all reasoning and tool calls"
          className="opacity-0 transition-opacity group-hover/work:opacity-100"
        />
      </div>

      {open && (
        <div className="animate-slide-up-fade space-y-1 border-t border-border/70 p-2">
          {children}
        </div>
      )}
    </div>
  );
}

function Count({
  icon,
  value,
  label,
}: {
  icon: React.ReactNode;
  value: number;
  label: string;
}) {
  return (
    <span className="flex items-center gap-1" title={label}>
      {icon}
      {value}
    </span>
  );
}
