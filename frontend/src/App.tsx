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

export default function App() {
  const [sources, setSources] = useState<string[]>([]);
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

  const { data: sessions, isLoading } = useQuery({
    queryKey: ["sessions", sources],
    queryFn: () => api.sessions({ sources: sources.length ? sources : undefined }),
  });

  // Closing the parent tab should not leave an orphaned subagent pane open.
  useEffect(() => {
    if (subagent && tabs.activeId === null) setSubagent(null);
  }, [subagent, tabs.activeId]);

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
    <TooltipProvider delayDuration={300}>
      <div className="flex h-full flex-col">
        <TopNav
          selected={sources}
          onSelectedChange={setSources}
          theme={theme}
          onThemeToggle={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
        />

        <div className="flex min-h-0 flex-1">
          <div className="w-[19rem] shrink-0">
            <SessionList
              sessions={sessions ?? []}
              activeId={tabs.activeId}
              openIds={tabs.tabs.map((t) => t.id)}
              loading={isLoading}
              onOpen={(session) => tabs.open(session)}
              onPin={(session) => tabs.open(session, true)}
            />
          </div>

          <div className="flex min-w-0 flex-1 flex-col">
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
          </div>
        </div>
      </div>
    </TooltipProvider>
  );
}
