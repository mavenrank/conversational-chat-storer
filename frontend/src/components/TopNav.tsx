import { useState } from "react";
import { DatabaseBackup, MessagesSquare, Moon, Settings, Sun, X } from "lucide-react";
import * as Dialog from "@radix-ui/react-dialog";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { formatBytes, formatTokens } from "@/lib/format";
import { Button } from "./ui/button";
import { SidebarTrigger } from "./ui/sidebar";
import { Tooltip, TooltipContent, TooltipTrigger } from "./ui/tooltip";

type NavProps = {
  theme: "dark" | "light";
  onThemeToggle: () => void;
  includeSubagents: boolean;
  onIncludeSubagentsChange: (value: boolean) => void;
};

export function TopNav(props: NavProps) {
  const { data: stats } = useQuery({ queryKey: ["stats"], queryFn: api.stats, refetchInterval: 30_000 });
  const { data: costs } = useQuery({ queryKey: ["costs"], queryFn: api.costs,
    refetchInterval: query => query.state.data?.running ? 2000 : 30_000 });
  return (
    <header className="flex h-12 min-w-0 shrink-0 items-center gap-2 border-b border-border bg-background px-2 sm:gap-3 sm:px-3">
      <SidebarTrigger />
      <div className="flex shrink-0 items-center gap-2">
        <span className="grid h-6 w-6 place-items-center rounded-md bg-primary text-xs font-bold text-primary-foreground">C</span>
        <span className="whitespace-nowrap text-[13px] font-semibold tracking-tight sm:text-sm">Chat Storer</span>
      </div>
      <div className="ml-auto flex min-w-0 items-center gap-1 sm:gap-2">
        {stats && <Tooltip>
          <TooltipTrigger asChild>
            <div className="hidden cursor-default items-center gap-3 pr-2 text-xs text-muted-foreground min-[540px]:flex">
              <Stat label="Chats" value={stats.session_count.toLocaleString()} />
              <span className="hidden min-[900px]:inline"><Stat label="Output" value={formatTokens(stats.output_tokens)} /></span>
              {stats.total_cost_usd > 0 && <span className="hidden min-[1100px]:inline"><Stat label="Recorded" value={`$${stats.total_cost_usd.toFixed(2)}`} /></span>}
            </div>
          </TooltipTrigger>
          <TooltipContent side="bottom" className="max-w-xs">
            <p className="mb-1.5 font-semibold">History totals</p>
            <Line label="Chats" value={stats.session_count} />
            <Line label="Output tokens" value={stats.output_tokens} />
            <Line label="Thinking tokens" value={stats.thinking_tokens} />
            <Line label="Input tokens" value={stats.input_tokens} />
            <Line label="Cached tokens" value={stats.cached_tokens} />
            <p className="mt-2">Recorded cost: ${stats.total_cost_usd.toFixed(2)}</p>
            {costs?.estimated_usd != null && <p>API estimates for other chats: ${costs.estimated_usd.toFixed(2)}{(costs.running || costs.unpriced_sessions > 0) && " · partial"}</p>}
            <p className="mt-2 text-muted-foreground">Token and cost totals include agent runs. Input and cache totals include context sent again on each request.</p>
          </TooltipContent>
        </Tooltip>}
        <span className="hidden items-center gap-1 text-xs tabular-nums text-muted-foreground min-[1000px]:flex"
          title={stats?.message_count_is_complete ? "Messages" : "Messages counted so far; full Codex counts load when chats are opened"}>
          <MessagesSquare size={13} />{stats?.message_count.toLocaleString() ?? "0"}{stats && !stats.message_count_is_complete && "+"}
        </span>
        <ArchiveButton />
        <Button variant="ghost" size="icon" onClick={props.onThemeToggle} aria-label="Toggle theme" title="Toggle theme">
          {props.theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
        </Button>
        <SettingsDialog {...props} />
      </div>
    </header>
  );
}

function SettingsDialog({ theme, onThemeToggle, includeSubagents, onIncludeSubagentsChange }: NavProps) {
  const { data: costs, error: costError, refetch, isFetching } = useQuery({
    queryKey: ["costs"], queryFn: api.costs,
    refetchInterval: query => query.state.data?.running ? 2000 : 30_000,
  });
  return <Dialog.Root>
    <Dialog.Trigger asChild><Button size="icon" aria-label="Settings" title="Settings"><Settings size={17} /></Button></Dialog.Trigger>
    <Dialog.Portal>
      <Dialog.Overlay className="fixed inset-0 z-50 bg-black/55 backdrop-blur-[2px]" />
      <Dialog.Content className="fixed left-1/2 top-1/2 z-50 max-h-[85dvh] w-[calc(100vw-32px)] max-w-md -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-xl border border-border bg-background p-5 shadow-2xl outline-none">
        <div className="flex items-center justify-between">
          <Dialog.Title className="text-base font-semibold">Settings</Dialog.Title>
          <Dialog.Close asChild><Button size="icon" aria-label="Close settings"><X size={16} /></Button></Dialog.Close>
        </div>
        <Dialog.Description className="mt-1 text-[13px] text-muted-foreground">Make your chat history comfortable to browse.</Dialog.Description>
        <section className="mt-6 space-y-3" aria-label="Appearance">
          <h3 className="text-[13px] font-semibold">Appearance</h3>
          <div className="flex items-center justify-between gap-4">
            <span className="text-[13px] text-muted-foreground">Theme</span>
            <div className="flex gap-1 rounded-lg border border-border p-1">
              <Button size="sm" variant={theme === "light" ? "secondary" : "ghost"} aria-pressed={theme === "light"} onClick={() => { if (theme !== "light") onThemeToggle(); }}><Sun size={14} />Light</Button>
              <Button size="sm" variant={theme === "dark" ? "secondary" : "ghost"} aria-pressed={theme === "dark"} onClick={() => { if (theme !== "dark") onThemeToggle(); }}><Moon size={14} />Dark</Button>
            </div>
          </div>
          <div className="flex justify-between text-[13px]"><span className="text-muted-foreground">Typeface</span><span>Geist Sans</span></div>
        </section>
        <section className="mt-5 space-y-3 border-t border-border pt-5" aria-label="Costs and pricing">
          <div className="flex items-center justify-between"><h3 className="text-[13px] font-semibold">Costs and pricing</h3>
            <Button size="sm" variant="ghost" onClick={() => refetch()} disabled={isFetching}>Recheck</Button></div>
          {costError ? <p className="text-xs text-destructive">Could not load costs. Use Recheck to try again.</p> : !costs ? <p className="text-xs text-muted-foreground">Loading costs…</p> : <>
            <div className="flex justify-between text-[13px]"><span className="text-muted-foreground">Recorded by sources</span><span className="tabular-nums">${costs.recorded_usd.toFixed(2)}</span></div>
            <div className="flex justify-between gap-3 text-[13px]"><span className="text-muted-foreground">API estimates for other chats</span><span className="tabular-nums">{costs.estimated_usd == null ? "Unavailable" : `$${costs.estimated_usd.toFixed(2)}`}</span></div>
            <p className="text-xs leading-relaxed text-muted-foreground">{costs.running ? `Calculating: ${costs.processed_sessions} of ${costs.session_count} chats and agent runs.` : `${costs.estimated_sessions} chats estimated · ${costs.unpriced_sessions} incomplete or unpriced.`} Estimates use current standard text API rates, including per-request context tiers. They are not subscription charges or historical invoices; tool fees and other billing modifiers are excluded.</p>
            {costs.unpriced_models.length > 0 && <details className="text-xs text-muted-foreground"><summary className="cursor-pointer">Models without verified rates</summary><p className="mt-2 break-words leading-relaxed">{costs.unpriced_models.join(", ")}</p></details>}
            <p className="text-xs text-muted-foreground">Rates checked {costs.rates_verified_at}. <span className="inline-flex flex-wrap gap-x-2">{costs.sources.map(source => <a key={source.name} href={source.url} target="_blank" rel="noreferrer" className="underline underline-offset-2 hover:text-foreground">{source.name}</a>)}</span></p>
          </>}
        </section>
        <section className="mt-5 space-y-3 border-t border-border pt-5" aria-label="History preferences">
          <h3 className="text-[13px] font-semibold">History</h3>
          <label className="flex cursor-pointer items-start gap-3 text-[13px]">
            <input type="checkbox" checked={includeSubagents} onChange={event => onIncludeSubagentsChange(event.target.checked)} className="mt-0.5 accent-[hsl(var(--primary))]" />
            <span>Show agent runs in history<span className="mt-1 block text-xs text-muted-foreground">Include delegated tasks and automatic reviews beside your chats.</span></span>
          </label>
          <p className="text-xs text-muted-foreground">Drag the sidebar divider to resize it. Use Ctrl+B to hide or show history.</p>
        </section>
      </Dialog.Content>
    </Dialog.Portal>
  </Dialog.Root>;
}

function ArchiveButton() {
  const client = useQueryClient();
  const { data } = useQuery({ queryKey: ["archive"], queryFn: api.archive.stats });
  const [result, setResult] = useState<string | null>(null);
  const run = useMutation({
    mutationFn: api.archive.run,
    onSuccess: r => {
      setResult(`+${r.added} new · ${r.updated} updated · ${r.unchanged} unchanged` + (r.failed ? ` · ${r.failed} failed` : ""));
      client.invalidateQueries({ queryKey: ["archive"] });
      setTimeout(() => setResult(null), 5000);
    },
    onError: error => setResult(String(error)),
  });
  return <Tooltip>
    <TooltipTrigger asChild><Button size="icon" onClick={() => run.mutate()} disabled={run.isPending} aria-label={run.isPending ? "Backing up chats" : "Back up chats"}>
      <DatabaseBackup size={16} className={run.isPending ? "animate-pulse" : undefined} />
    </Button></TooltipTrigger>
    <TooltipContent side="bottom" className="max-w-xs">
      {result ? <p className="font-semibold">{result}</p> : <div className="space-y-1">
        <p className="font-semibold">Back up all chats</p>
        <p className="text-muted-foreground">Save a local copy so history survives an app pruning or replacing its store.</p>
        {data && <p className="pt-1 text-muted-foreground">{data.session_count} archived · {formatBytes(data.size_bytes)}<br />{data.root}</p>}
      </div>}
    </TooltipContent>
  </Tooltip>;
}

function Stat({ label, value }: { label: string; value: string }) {
  return <span className="inline-flex items-baseline gap-1.5 whitespace-nowrap"><span>{label}</span><span className="font-medium tabular-nums text-foreground">{value}</span></span>;
}
function Line({ label, value }: { label: string; value: number }) {
  return <div className="flex justify-between gap-4"><span>{label}</span><span className="tabular-nums">{value.toLocaleString()}</span></div>;
}
