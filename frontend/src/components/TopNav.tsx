import { useState } from "react";
import { DatabaseBackup, MessagesSquare, Moon, Sun } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { formatBytes, formatTokens } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Separator } from "./ui/separator";
import { ToggleGroup, ToggleGroupItem } from "./ui/toggle-group";
import { Tooltip, TooltipContent, TooltipTrigger } from "./ui/tooltip";

/* The colour identifies the tool, so the name is set in it directly rather
   than pairing a coloured dot with plain text. */
const SOURCE_TEXT: Record<string, string> = {
  opencode: "text-opencode",
  gemini: "text-gemini",
  kilocode: "text-kilocode",
  codex: "text-codex",
  claude: "text-claude",
};

export function TopNav({
  selected,
  onSelectedChange,
  theme,
  onThemeToggle,
}: {
  selected: string[];
  onSelectedChange: (next: string[]) => void;
  theme: "dark" | "light";
  onThemeToggle: () => void;
}) {
  const { data: sources } = useQuery({ queryKey: ["sources"], queryFn: api.sources });
  const { data: stats } = useQuery({ queryKey: ["stats"], queryFn: api.stats });

  return (
    <header className="flex h-14 shrink-0 items-center gap-4 border-b border-border bg-background px-5">
      <div className="flex items-center gap-2">
        <span className="grid h-7 w-7 place-items-center rounded-md bg-primary text-sm font-black text-primary-foreground">
          C
        </span>
        <span className="display text-base">Chat Storer</span>
      </div>

      <Separator orientation="vertical" className="mx-1 h-5" />

      {/*
        Multi-select toggle group. Empty selection means "all sources" — the
        enabled/disabled state is what the toggles express.
      */}
      <ToggleGroup
        type="multiple"
        size="sm"
        value={selected}
        onValueChange={onSelectedChange}
      >
        {sources?.map((source) => (
          <Tooltip key={source.id}>
            <TooltipTrigger asChild>
              <ToggleGroupItem
                value={source.id}
                disabled={!source.available}
                aria-label={source.display_name}
                className={cn(
                  "gap-1.5",
                  selected.length > 0 &&
                    !selected.includes(source.id) &&
                    "opacity-45",
                )}
              >
                <span
                  className={cn(
                    "font-semibold",
                    source.available
                      ? (SOURCE_TEXT[source.id] ?? "text-foreground")
                      : "text-muted-foreground",
                  )}
                >
                  {source.display_name}
                </span>
                {source.available && (
                  <span className="mono text-xs text-muted-foreground">
                    {source.session_count}
                  </span>
                )}
              </ToggleGroupItem>
            </TooltipTrigger>
            <TooltipContent>
              {source.available ? (
                <span className="mono">{source.root}</span>
              ) : (
                <span>{source.error ?? "not found on this machine"}</span>
              )}
            </TooltipContent>
          </Tooltip>
        ))}
      </ToggleGroup>

      <div className="ml-auto flex items-center gap-3">
        {stats && (
          <Tooltip>
            <TooltipTrigger asChild>
              <div className="flex cursor-default items-center gap-4 text-xs text-muted-foreground">
                <Stat label="sessions" value={stats.session_count.toLocaleString()} />
                <Stat label="output" value={formatTokens(stats.output_tokens)} />
                {stats.total_cost_usd > 0 && (
                  <Stat label="cost" value={`$${stats.total_cost_usd.toFixed(2)}`} />
                )}
              </div>
            </TooltipTrigger>
            <TooltipContent side="bottom" className="max-w-xs">
              <div className="space-y-2">
                <div>
                  <p className="font-semibold">Text generated</p>
                  <Line label="Output" value={stats.output_tokens} />
                  <Line label="Thinking" value={stats.thinking_tokens} />
                </div>
                <div className="border-t border-border pt-1.5">
                  <p className="font-semibold text-muted-foreground">
                    Context re-sent (per request)
                  </p>
                  <Line label="Input" value={stats.input_tokens} />
                  <Line label="Cache reads" value={stats.cached_tokens} />
                </div>
                <p className="border-t border-border pt-1.5 text-muted-foreground">
                  An agent resends the whole conversation on every request, so
                  the second group counts the same context over and over — here
                  about{" "}
                  {Math.round(stats.cached_tokens / Math.max(stats.output_tokens, 1))}x
                  the text actually generated. It is not additional work, and
                  cache reads are billed at a fraction of the input rate.
                </p>
                <p className="text-muted-foreground">
                  Totals include subagent runs, which are hidden from the
                  session list but still cost money.
                </p>
              </div>
            </TooltipContent>
          </Tooltip>
        )}

        <Badge variant="outline" className="mono gap-1 normal-case">
          <MessagesSquare size={11} />
          {stats?.message_count.toLocaleString() ?? "0"}
        </Badge>

        <ArchiveButton />

        <Button
          variant="ghost"
          size="icon"
          onClick={onThemeToggle}
          aria-label="Toggle theme"
        >
          {theme === "dark" ? <Sun size={15} /> : <Moon size={15} />}
        </Button>
      </div>
    </header>
  );
}

/**
 * Snapshots every session into the local archive. Content-hashed server-side,
 * so repeat runs only write what actually changed.
 */
function ArchiveButton() {
  const client = useQueryClient();
  const { data } = useQuery({ queryKey: ["archive"], queryFn: api.archive.stats });
  const [result, setResult] = useState<string | null>(null);

  const run = useMutation({
    mutationFn: api.archive.run,
    onSuccess: (r) => {
      setResult(
        `+${r.added} new · ${r.updated} updated · ${r.unchanged} unchanged` +
          (r.failed ? ` · ${r.failed} failed` : ""),
      );
      client.invalidateQueries({ queryKey: ["archive"] });
      setTimeout(() => setResult(null), 5000);
    },
    onError: (error) => setResult(String(error)),
  });

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          onClick={() => run.mutate()}
          disabled={run.isPending}
        >
          <DatabaseBackup
            size={14}
            className={run.isPending ? "animate-pulse" : undefined}
          />
          {run.isPending ? "Backing up…" : "Backup"}
          {data && data.session_count > 0 && (
            <span className="mono text-xs text-muted-foreground">
              {data.session_count}
            </span>
          )}
        </Button>
      </TooltipTrigger>
      <TooltipContent side="bottom" className="max-w-xs">
        {result ? (
          <p className="font-semibold">{result}</p>
        ) : (
          <div className="space-y-1">
            <p className="font-semibold">Back up all sessions</p>
            <p className="text-muted-foreground">
              Copies every session into a local archive in this app's own
              normalised format, so history survives a tool pruning its store or
              being reinstalled.
            </p>
            {data && (
              <p className="mono pt-1">
                {data.session_count} archived · {formatBytes(data.size_bytes)}
                <br />
                {data.root}
              </p>
            )}
          </div>
        )}
      </TooltipContent>
    </Tooltip>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <span className="flex items-baseline gap-1">
      <span className="label-caps text-muted-foreground/70">{label}</span>
      <span className="mono text-[13px] font-semibold text-foreground">{value}</span>
    </span>
  );
}

function Line({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex justify-between gap-4">
      <span>{label}</span>
      <span className="mono">{value.toLocaleString()}</span>
    </div>
  );
}
