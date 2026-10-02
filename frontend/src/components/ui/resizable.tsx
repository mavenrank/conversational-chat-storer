import type { ComponentProps } from "react";
import { GripVertical } from "lucide-react";
import { Group, Panel, Separator } from "react-resizable-panels";
import { cn } from "@/lib/utils";

// shadcn/ui's resizable composition, using the v4 panel primitives.
export function ResizablePanelGroup({
  className,
  ...props
}: ComponentProps<typeof Group>) {
  return (
    <Group
      data-slot="resizable-panel-group"
      className={cn("h-full w-full min-w-0", className)}
      {...props}
    />
  );
}

export const ResizablePanel = Panel;

export function ResizableHandle({
  className,
  withHandle = false,
  ...props
}: ComponentProps<typeof Separator> & { withHandle?: boolean }) {
  return (
    <Separator
      data-slot="resizable-handle"
      className={cn(
        "resize-handle relative z-10 flex w-[5px] shrink-0 items-center justify-center bg-border/60",
        "transition-colors hover:bg-ring/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        className,
      )}
      {...props}
    >
      {withHandle && (
        <span className="grid h-8 w-[11px] place-items-center rounded-full border border-border bg-background text-muted-foreground">
          <GripVertical size={11} />
        </span>
      )}
    </Separator>
  );
}
