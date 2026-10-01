import { useMemo, type ReactNode } from "react";
import { Check, GitBranch, Search, X } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { SessionSummary } from "@/lib/types";
import { formatDateTime, formatRelative, formatTokens } from "@/lib/format";
import { SOURCE_STYLE } from "@/lib/sources";
import { cn } from "@/lib/utils";
import { SourceIcon } from "./SourceIcon";
import { SidebarContent, SidebarFooter, SidebarHeader, SidebarMenu, SidebarMenuButton, SidebarMenuItem } from "./ui/sidebar";
import { ToggleGroup, ToggleGroupItem } from "./ui/toggle-group";

export function SessionList({ sessions, sources, onSourcesChange, filter, onFilterChange, activeId, openIds, loading, includeSubagents, onIncludeSubagentsChange, onOpen, onPin }: {
  sessions: SessionSummary[];
  sources: string[];
  onSourcesChange: (value: string[]) => void;
  filter: string;
  onFilterChange: (value: string) => void;
  activeId: string | null;
  openIds: string[];
  loading: boolean;
  includeSubagents: boolean;
  onIncludeSubagentsChange: (value: boolean) => void;
  onOpen: (session: SessionSummary) => void;
  onPin: (session: SessionSummary) => void;
}) {
  const open = useMemo(() => new Set(openIds), [openIds]);
  const { data: availableSources } = useQuery({ queryKey: ["sources"], queryFn: api.sources, refetchInterval: 30_000 });
  const visible = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    return needle ? sessions.filter(s => s.title.toLowerCase().includes(needle) || s.cwd.toLowerCase().includes(needle) || s.models.some(m => m.toLowerCase().includes(needle))) : sessions;
  }, [sessions, filter]);

  return (
    <div className="flex h-full min-w-0 flex-col">
      <SidebarHeader className="gap-2.5">
        <div className="flex items-center justify-between">
          <h2 className="text-[13px] font-semibold">History</h2>
          <div className="flex items-center gap-2">
            {sources.length > 0 && <button type="button" onClick={() => onSourcesChange([])} className="rounded px-1.5 py-0.5 text-[11px] text-muted-foreground hover:bg-accent hover:text-foreground" title="Show all sources">All sources</button>}
            <span className="text-xs tabular-nums text-muted-foreground">{loading ? "Loading…" : `${visible.length} ${visible.length === 1 ? "chat" : "chats"}`}</span>
          </div>
        </div>
        <ToggleGroup type="multiple" value={sources} onValueChange={onSourcesChange} size="sm" aria-label="Filter chat sources" className="grid grid-cols-5 gap-1">
          {availableSources?.map(source => {
            const style = SOURCE_STYLE[source.id];
            return <ToggleGroupItem key={source.id} value={source.id} disabled={!source.available} aria-label={source.display_name}
              title={source.available ? `${source.display_name}: ${source.session_count} chats` : source.error ?? "No local history found"}
              className={cn("h-8 min-w-0 justify-center gap-1 rounded-md border border-border/70 px-1", sources.length === 0 || sources.includes(source.id) ? "bg-background" : "opacity-50")}>
              <SourceIcon source={source.id} className={cn("h-4 w-4", style.text)} />
              <span className="text-[10px] tabular-nums text-muted-foreground">{source.session_count}</span>
            </ToggleGroupItem>;
          })}
        </ToggleGroup>
        <div className="flex h-9 items-center gap-2 rounded-md border border-input bg-background px-2.5 focus-within:border-ring">
          <Search size={14} className="shrink-0 text-muted-foreground" />
          <input value={filter} onChange={event => onFilterChange(event.target.value)} placeholder="Search chats" aria-label="Search chats"
            className="min-w-0 flex-1 bg-transparent text-[13px] placeholder:text-muted-foreground focus:outline-none" />
          {filter && <button type="button" onClick={() => onFilterChange("")} aria-label="Clear search" className="rounded p-0.5 text-muted-foreground hover:text-foreground"><X size={13} /></button>}
        </div>
      </SidebarHeader>

      <SidebarContent>
        {loading && <Empty>Loading chats…</Empty>}
        {!loading && visible.length === 0 && <Empty>No chats match your search.</Empty>}
        <SidebarMenu>
          {visible.map(session => {
            const active = activeId === session.id;
            const style = SOURCE_STYLE[session.source];
            return <SidebarMenuItem key={session.id}>
              <SidebarMenuButton isActive={active} onClick={() => onOpen(session)} onDoubleClick={() => onPin(session)}
                title={`${session.title}\n${session.models.join(", ")}\n${formatTokens(session.usage.output_tokens)} tokens generated\n${session.cwd}`}
                className={cn("pl-4", active ? style.active : "hover:bg-sidebar-accent")}>
                <span className={cn("absolute left-0 rounded-r-full", style.rail, active ? "inset-y-0 w-1.5" : "inset-y-2 w-1")} />
                <div className="flex items-start gap-2">
                  <span className={cn("line-clamp-2 min-w-0 flex-1 text-[13px] leading-[1.45] text-foreground", active ? "font-semibold" : "font-medium")}>{session.title || "Untitled chat"}</span>
                  {active && <span className={cn("mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded-full", style.rail)} title="Selected chat"><Check size={11} strokeWidth={3} className="text-background" /></span>}
                  {open.has(session.id) && !active && <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-muted-foreground" title="Open in a tab" />}
                </div>
                <div className="mt-2 flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-muted-foreground">
                  <span className={cn("inline-flex shrink-0 items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-semibold", style.background, style.text)}>
                    <SourceIcon source={session.source} className="h-3 w-3" />{style.label}
                  </span>
                  <span className="shrink-0 tabular-nums" title={formatDateTime(session.updated_at ?? session.created_at)}>{formatRelative(session.updated_at ?? session.created_at)}</span>
                  {session.counts_exact && session.user_message_count > 0 && <span className="shrink-0 tabular-nums" title={`${session.user_message_count} prompts · ${session.message_count} turns`}>{session.user_message_count} prompts</span>}
                  {session.subagent_count > 0 && <span className="ml-auto flex shrink-0 items-center gap-1 text-agent" title={`${session.subagent_count} agent runs`}><GitBranch size={11} />{session.subagent_count}</span>}
                </div>
                {(session.project?.name || session.is_archived || session.is_subagent) && <div className="mt-1 flex items-center gap-2 text-[11px] text-muted-foreground/80">
                  {session.is_archived && <span>Archived</span>}
                  {session.is_subagent && <span className="text-agent">Agent run</span>}
                  {session.project?.name && <span className="truncate" title={session.cwd}>{session.project.name}</span>}
                </div>}
              </SidebarMenuButton>
            </SidebarMenuItem>;
          })}
        </SidebarMenu>
      </SidebarContent>
      <SidebarFooter className="px-3 py-2.5">
        <label className="flex cursor-pointer items-center gap-2 text-xs text-muted-foreground">
          <input type="checkbox" checked={includeSubagents} onChange={event => onIncludeSubagentsChange(event.target.checked)} className="accent-[hsl(var(--primary))]" />
          Include agent runs
        </label>
      </SidebarFooter>
    </div>
  );
}

function Empty({ children }: { children: ReactNode }) {
  return <div className="p-4 text-[13px] text-muted-foreground">{children}</div>;
}
