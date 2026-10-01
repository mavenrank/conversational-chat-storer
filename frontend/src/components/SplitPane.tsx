import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { GitBranch, X } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Two-column resizable split. The right pane is optional; when absent the left
 * fills the width, so the same component covers both "transcript only" and
 * "transcript + subagent".
 *
 * The divider drives a width in percent held in state, and pointer capture keeps
 * the drag alive when the cursor outruns the 4px handle.
 */
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
  const containerRef = useRef<HTMLDivElement>(null);
  const [leftPercent, setLeftPercent] = useState(58);
  const [dragging, setDragging] = useState(false);

  const onPointerMove = useCallback(
    (event: PointerEvent) => {
      const container = containerRef.current;
      if (!container) return;
      const rect = container.getBoundingClientRect();
      const ratio = ((event.clientX - rect.left) / rect.width) * 100;
      setLeftPercent(Math.min(80, Math.max(25, ratio)));
    },
    [],
  );

  useEffect(() => {
    if (!dragging) return;
    const stop = () => setDragging(false);
    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", stop);
    // Stop text selection fighting the drag.
    document.body.style.userSelect = "none";
    document.body.style.cursor = "col-resize";
    return () => {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", stop);
      document.body.style.userSelect = "";
      document.body.style.cursor = "";
    };
  }, [dragging, onPointerMove]);

  const hasRight = Boolean(right);

  return (
    <div ref={containerRef} className="flex min-h-0 flex-1">
      <div
        className="min-w-0"
        style={{ width: hasRight ? `${leftPercent}%` : "100%" }}
      >
        {left}
      </div>

      {hasRight && (
        <>
          <div
            role="separator"
            aria-orientation="vertical"
            onPointerDown={() => setDragging(true)}
            onDoubleClick={() => setLeftPercent(58)}
            className={cn(
              "group/divider relative w-px shrink-0 cursor-col-resize bg-border",
              "transition-colors ease-swift hover:bg-ring",
              dragging && "bg-ring",
            )}
          >
            {/* Widen the hit area without widening the visual line. */}
            <span className="absolute inset-y-0 -left-1.5 -right-1.5" />
          </div>

          <aside
            className="animate-slide-in-right flex min-w-0 flex-col"
            style={{ width: `${100 - leftPercent}%` }}
          >
            <div className="flex h-11 shrink-0 items-center gap-2.5 border-b border-border bg-muted/40 px-4">
              <GitBranch size={14} className="shrink-0 text-agent" />
              <span className="min-w-0 flex-1 truncate text-[13px] font-semibold">
                {rightTitle}
              </span>
              <button
                type="button"
                onClick={onCloseRight}
                aria-label="Close subagent pane"
                className="rounded-sm px-1.5 text-muted-foreground transition-colors ease-swift hover:bg-accent hover:text-foreground"
              >
                <X size={14} />
              </button>
            </div>
            <div className="min-h-0 flex-1">{right}</div>
          </aside>
        </>
      )}
    </div>
  );
}
