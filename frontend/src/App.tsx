import { useCallback, useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useTabs } from "@/hooks/useTabs";
import { TopNav } from "@/components/TopNav";
import { TabBar } from "@/components/TabBar";
import { SessionList } from "@/components/SessionList";
import { SplitPane } from "@/components/SplitPane";
import { TranscriptView } from "@/components/TranscriptView";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Sidebar, SidebarInset, SidebarProvider, useSidebar } from "@/components/ui/sidebar";
import { ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable";

export default function App() {
  return <TooltipProvider delayDuration={300}><SidebarProvider><AppContent /></SidebarProvider></TooltipProvider>;
}

function AppContent() {
  const { isMobile, setOpenMobile } = useSidebar();
  const [sources, setSources] = useState<string[]>([]);
  const [filter, setFilter] = useState("");
  const [includeSubagents, setIncludeSubagents] = useState(() => localStorage.getItem("ccsweb.includeAgentRuns") === "true");
  const [theme, setTheme] = useState<"dark" | "light">(
    () => (localStorage.getItem("ccsweb.theme") as "dark" | "light") ?? "dark",
  );
  /** Subagent session opened in the right pane, if any. */
  const [subagent, setSubagent] = useState<{ id: string; title: string } | null>(null);

  const tabs = useTabs();

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    localStorage.setItem("ccsweb.theme", theme);
  }, [theme]);
  useEffect(() => { localStorage.setItem("ccsweb.includeAgentRuns", String(includeSubagents)); }, [includeSubagents]);

  const { data: sessions, isLoading } = useQuery({
    queryKey: ["sessions", sources, includeSubagents],
    queryFn: () => api.sessions({ sources: sources.length ? sources : undefined, includeSubagents }),
    staleTime: 5000,
    refetchInterval: 10_000,
  });

  // Switching or closing the parent must not leave a different chat's agent run open.
  useEffect(() => {
    setSubagent(null);
  }, [tabs.activeId]);

  const { cycle, close, activeId } = tabs;
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.ctrlKey && event.key === "Tab") {
        event.preventDefault();
        cycle(event.shiftKey ? -1 : 1);
      }
      if (event.ctrlKey && event.key.toLowerCase() === "w" && activeId) {
        event.preventDefault();
        close(activeId);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [cycle, close, activeId]);

  const openSubagent = useCallback((id: string, title: string) => {
    setSubagent({ id, title });
  }, []);

  return (
      <>
        <TopNav
          theme={theme}
          onThemeToggle={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
          includeSubagents={includeSubagents}
          onIncludeSubagentsChange={setIncludeSubagents}
        />

        <ResizablePanelGroup orientation="horizontal" className="min-h-0 flex-1" id="history-layout">
          <Sidebar>
            <SessionList
              sources={sources}
              onSourcesChange={setSources}
              filter={filter}
              onFilterChange={setFilter}
              sessions={sessions ?? []}
              activeId={tabs.activeId}
              openIds={tabs.tabs.map((t) => t.id)}
              loading={isLoading}
              includeSubagents={includeSubagents}
              onIncludeSubagentsChange={setIncludeSubagents}
              onOpen={(session) => { tabs.open(session); setSubagent(null); if (isMobile) setOpenMobile(false); }}
              onPin={(session) => tabs.open(session, true)}
            />
          </Sidebar>

          <ResizablePanel id="reader" minSize={isMobile ? 0 : 340}>
          <SidebarInset>
            <TabBar
              tabs={tabs.tabs}
              activeId={tabs.activeId}
              onActivate={tabs.activate}
              onClose={tabs.close}
              onPin={tabs.pin}
            />

            <SplitPane
              left={
                <TranscriptView
                  sessionId={tabs.activeId}
                  onOpenSubagent={openSubagent}
                />
              }
              right={
                subagent ? (
                  <TranscriptView
                    sessionId={subagent.id}
                    onOpenSubagent={openSubagent}
                    compact
                  />
                ) : null
              }
              rightTitle={subagent?.title}
              onCloseRight={() => setSubagent(null)}
            />
          </SidebarInset>
          </ResizablePanel>
        </ResizablePanelGroup>
      </>
  );
}
