import { useState, type MouseEvent } from "react";
import { Check, Copy } from "lucide-react";
import { cn } from "@/lib/utils";

interface CopyButtonProps {
  /** Resolved lazily so content that has not been fetched yet can still be copied. */
  value: string | (() => string | Promise<string>);
  label?: string;
  /** Tooltip. Falls back to the label when absent. */
  title?: string;
  className?: string;
}

export function CopyButton({ value, label, title, className }: CopyButtonProps) {
  const [copied, setCopied] = useState(false);

  async function copy(event: MouseEvent) {
    event.stopPropagation();
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
      document.execCommand("copy");
      textarea.remove();
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 1400);
  }

  return (
    <button
      type="button"
      onClick={copy}
      title={title ?? label ?? "Copy"}
      className={cn(
        "inline-flex shrink-0 items-center gap-1.5 rounded-md px-2 py-1 text-xs",
        copied ? "text-add" : "text-muted-foreground hover:bg-accent hover:text-foreground",
        className,
      )}
    >
      {copied ? <Check size={13} strokeWidth={2.5} /> : <Copy size={13} />}
      {label && <span>{copied ? "copied" : label}</span>}
    </button>
  );
}
