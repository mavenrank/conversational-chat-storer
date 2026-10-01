import { useState, type ReactNode } from "react";
import { ChevronRight } from "lucide-react";
import { formatBytes } from "@/lib/format";
import { cn } from "@/lib/utils";

export type Tone =
  | "read"
  | "write"
  | "edit"
  | "command"
  | "search"
  | "agent"
  | "think"
  | "plain";

const RAIL: Record<Tone, string> = {
  read: "bg-read",
  write: "bg-write",
  edit: "bg-edit",
  command: "bg-command",
  search: "bg-search",
  agent: "bg-agent",
  think: "bg-muted-foreground/40",
  plain: "bg-border",
};

interface AccordionProps {
  icon?: ReactNode;
  label: ReactNode;
  meta?: ReactNode;
  sizeBytes?: number;
  tone?: Tone;
  error?: boolean;
  /** Fired once, the first time the row opens — backs lazy fetching. */
  onFirstOpen?: () => void;
  children: ReactNode;
}

/**
 * A single-line row, not a card. Type is carried by a rail on the left rather
 * than a full border box, so a turn with a dozen tool calls reads as a list.
 * The body only mounts once opened.
 */
export function Accordion({
  icon,
  label,
  meta,
  sizeBytes,
  tone = "plain",
  error = false,
  onFirstOpen,
  children,
}: AccordionProps) {
  const [open, setOpen] = useState(false);
  const [opened, setOpened] = useState(false);

  function toggle() {
    const next = !open;
    setOpen(next);
    if (next && !opened) {
      setOpened(true);
      onFirstOpen?.();
    }
  }

  return (
    <div className="group/row relative overflow-hidden rounded-md">
      <span
        className={cn(
          "absolute left-0 top-0 h-full w-[2.5px]",
          error ? "bg-destructive" : RAIL[tone],
          "opacity-70 transition-opacity ease-swift group-hover/row:opacity-100",
        )}
      />
      <button
        type="button"
        onClick={toggle}
        className={cn(
          "flex w-full items-center gap-2.5 py-2 pl-4 pr-3 text-left",
          "transition-colors ease-swift hover:bg-accent/60",
          open && "bg-accent/40",
        )}
      >
        <ChevronRight
          size={14}
          strokeWidth={2.5}
          className={cn(
            "shrink-0 text-muted-foreground transition-transform duration-200 ease-swift",
            open && "rotate-90",
          )}
        />
        {icon}
        <span className="min-w-0 flex-1 truncate text-sm">{label}</span>
        {meta}
        {sizeBytes != null && sizeBytes > 0 && (
          <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
            {formatBytes(sizeBytes)}
          </span>
        )}
      </button>
      {open && (
        <div className="animate-slide-up-fade ml-4 mt-1 rounded-md border border-border bg-muted/30">
          {children}
        </div>
      )}
    </div>
  );
}
