import { X } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Tab } from "@/hooks/useTabs";

const SOURCE_DOT: Record<string, string> = {
  opencode: "bg-opencode",
  gemini: "bg-gemini",
  kilocode: "bg-kilocode",
  codex: "bg-codex",
  claude: "bg-claude",
};

export function TabBar({
  tabs,
  activeId,
  onActivate,
  onClose,
  onPin,
}: {
  tabs: Tab[];
  activeId: string | null;
  onActivate: (id: string) => void;
  onClose: (id: string) => void;
  onPin: (id: string) => void;
}) {
  if (tabs.length === 0) return null;

  return (
    <div className="flex h-11 shrink-0 items-stretch gap-1 overflow-x-auto border-b border-border bg-muted/40 px-2 pt-1.5">
      {tabs.map((tab) => {
        const active = tab.id === activeId;
        return (
          <div
            key={tab.id}
            role="tab"
            aria-selected={active}
            tabIndex={0}
            onClick={() => onActivate(tab.id)}
            onDoubleClick={() => onPin(tab.id)}
            onAuxClick={(event) => {
              // Middle-click closes, as in a browser.
              if (event.button === 1) {
                event.preventDefault();
                onClose(tab.id);
              }
            }}
            className={cn(
              "group/tab relative flex min-w-[10rem] max-w-[18rem] cursor-pointer items-center gap-2.5",
              "rounded-t-lg px-4 text-sm transition-colors ease-swift",
              "animate-slide-up-fade",
              active
                ? "bg-background font-semibold text-foreground"
                : "text-muted-foreground hover:bg-background/50 hover:text-foreground",
            )}
          >
            <span
              className={cn(
                "h-1.5 w-1.5 shrink-0 rounded-full",
                SOURCE_DOT[tab.source] ?? "bg-muted-foreground",
              )}
            />
            <span
              className={cn(
                "min-w-0 flex-1 truncate",
                tab.preview && "italic font-normal",
              )}
              title={tab.title}
            >
              {tab.title}
            </span>
            <button
              type="button"
              aria-label="Close tab"
              onClick={(event) => {
                event.stopPropagation();
                onClose(tab.id);
              }}
              className={cn(
                "shrink-0 rounded-sm px-1 text-muted-foreground opacity-0 transition-opacity",
                "hover:bg-accent hover:text-foreground group-hover/tab:opacity-100",
                active && "opacity-60",
              )}
            >
              <X size={13} />
            </button>
            {active && (
              <span className="absolute inset-x-0 -bottom-px h-px bg-background" />
            )}
          </div>
        );
      })}
    </div>
  );
}
