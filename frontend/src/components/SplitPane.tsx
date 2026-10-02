import { useEffect, useRef, useState, type ReactNode } from "react";
import { ArrowLeft, GitBranch, X } from "lucide-react";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "./ui/resizable";
import { Button } from "./ui/button";

export function SplitPane({
  left,
  right,
  onCloseRight,
  rightTitle,
}: {
  left: ReactNode;
  right?: ReactNode | null;
  onCloseRight?: () => void;
  rightTitle?: ReactNode;
}) {
  const container = useRef<HTMLDivElement>(null);
  const [wide, setWide] = useState(false);
  const [initialLayout] = useState(() => {
    try {
      return (
        JSON.parse(
          localStorage.getItem("ccsweb.transcript.layout") ?? "null",
        ) ?? undefined
      );
    } catch {
      return undefined;
    }
  });
  useEffect(() => {
    const element = container.current;
    if (!element) return;
    const observer = new ResizeObserver((entries) =>
      setWide(entries[0].contentRect.width >= 760),
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const review = (
    <aside className="flex h-full min-w-0 flex-col" aria-label="Agent run">
      <div className="flex h-10 shrink-0 items-center gap-2 border-b border-border bg-muted/30 px-3">
        {!wide && (
          <Button size="sm" onClick={onCloseRight} className="h-7 px-1.5">
            <ArrowLeft size={14} />
            Back to chat
          </Button>
        )}
        <GitBranch size={14} className="shrink-0 text-agent" />
        <span className="min-w-0 flex-1 truncate text-xs font-medium">
          {rightTitle}
        </span>
        <Button
          size="icon"
          onClick={onCloseRight}
          aria-label="Close agent run"
          className="h-7 w-7"
        >
          <X size={14} />
        </Button>
      </div>
      <div className="min-h-0 flex-1">{right}</div>
    </aside>
  );

  return (
    <div
      ref={container}
      className="min-h-0 min-w-0 flex-1"
      data-layout={wide && right ? "split" : "single"}
    >
      {wide && right ? (
        <ResizablePanelGroup
          orientation="horizontal"
          id="transcript-layout"
          defaultLayout={initialLayout}
          onLayoutChanged={(layout, meta) => {
            if (meta.isUserInteraction)
              localStorage.setItem(
                "ccsweb.transcript.layout",
                JSON.stringify(layout),
              );
          }}
        >
          <ResizablePanel
            id="parent-transcript"
            defaultSize="55%"
            minSize={340}
          >
            {left}
          </ResizablePanel>
          <ResizableHandle withHandle aria-label="Resize transcript panes" />
          <ResizablePanel id="agent-transcript" defaultSize="45%" minSize={320}>
            {review}
          </ResizablePanel>
        </ResizablePanelGroup>
      ) : (
        <div className="h-full min-w-0">
          <div className={right ? "hidden" : "h-full"}>{left}</div>
          {right && review}
        </div>
      )}
    </div>
  );
}
