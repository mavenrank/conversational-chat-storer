import { useEffect, useRef, useState, type MouseEvent } from "react";
import { AlertCircle, Check, Copy, LoaderCircle } from "lucide-react";
import { cn } from "@/lib/utils";

interface CopyButtonProps {
  /** Resolved lazily so content that has not been fetched yet can still be copied. */
  value: string | (() => string | Promise<string>);
  label?: string;
  /** Tooltip. Falls back to the label when absent. */
  title?: string;
  className?: string;
}

export function CopyButton({
  value,
  label,
  title,
  className,
}: CopyButtonProps) {
  const [state, setState] = useState<"ready" | "copying" | "copied" | "error">(
    "ready",
  );
  const reset = useRef<ReturnType<typeof setTimeout>>();
  useEffect(() => () => clearTimeout(reset.current), []);
  const action = title ?? label ?? "Copy";
  const feedback =
    state === "copied"
      ? "Copied"
      : state === "error"
        ? "Copy failed — try again"
        : state === "copying"
          ? "Copying…"
          : action;

  async function copy(event: MouseEvent) {
    event.stopPropagation();
    clearTimeout(reset.current);
    setState("copying");
    try {
      const text = typeof value === "function" ? await value() : value;
      try {
        await navigator.clipboard.writeText(text);
      } catch {
        // Clipboard API needs a secure context; fall back so copying still works
        // when the app is served over plain http.
        const textarea = document.createElement("textarea");
        textarea.value = text;
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";
        document.body.appendChild(textarea);
        textarea.select();
        try {
          if (!document.execCommand("copy"))
            throw new Error("Clipboard unavailable");
        } finally {
          textarea.remove();
        }
      }
      setState("copied");
    } catch {
      setState("error");
    }
    reset.current = setTimeout(() => setState("ready"), 1800);
  }

  return (
    <button
      type="button"
      onClick={copy}
      title={feedback}
      aria-label={state === "ready" ? action : `${feedback}: ${action}`}
      aria-busy={state === "copying"}
      disabled={state === "copying"}
      className={cn(
        "inline-flex shrink-0 items-center gap-1.5 rounded-md px-2 py-1 text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-wait",
        state === "copied"
          ? "text-add"
          : state === "error"
            ? "text-destructive"
            : "text-muted-foreground hover:bg-accent hover:text-foreground",
        className,
      )}
    >
      {state === "copied" ? (
        <Check size={13} strokeWidth={2.5} />
      ) : state === "copying" ? (
        <LoaderCircle size={13} className="animate-spin" />
      ) : state === "error" ? (
        <AlertCircle size={13} />
      ) : (
        <Copy size={13} />
      )}
      {label && <span>{state === "ready" ? label : feedback}</span>}
      <span className="sr-only" role="status">
        {state === "ready" ? "" : feedback}
      </span>
    </button>
  );
}
