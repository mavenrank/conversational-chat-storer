import { X } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Tab } from "@/hooks/useTabs";
import { SOURCE_STYLE } from "@/lib/sources";
import { SourceIcon } from "./SourceIcon";
import type { SourceId } from "@/lib/types";

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
    <div
      role="tablist"
      aria-label="Open chats"
      className="flex h-9 shrink-0 items-stretch gap-1 overflow-x-auto border-b border-border bg-muted/30 px-2 pt-1"
    >
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
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                onActivate(tab.id);
              }
            }}
            onAuxClick={(event) => {
              // Middle-click closes, as in a browser.
              if (event.button === 1) {
                event.preventDefault();
                onClose(tab.id);
              }
            }}
            className={cn(
              "group/tab relative flex min-w-[8rem] max-w-[16rem] shrink-0 cursor-pointer items-center gap-2",
              "rounded-t-md px-3 text-xs transition-colors ease-swift focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring",
              "animate-slide-up-fade",
              active
                ? "bg-background font-semibold text-foreground"
                : "text-muted-foreground hover:bg-background/50 hover:text-foreground",
            )}
          >
            <SourceIcon
              source={tab.source as SourceId}
              className={cn(
                "h-3.5 w-3.5",
                SOURCE_STYLE[tab.source as SourceId]?.text,
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
                "shrink-0 rounded-sm px-1 text-muted-foreground opacity-60 transition-opacity",
                "hover:bg-accent hover:text-foreground group-hover/tab:opacity-100",
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
