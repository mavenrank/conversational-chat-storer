import { useEffect, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";
import { api } from "@/lib/api";
import { copyOptions, resolveCopyText, type CopyScope } from "@/lib/copy";
import type { Message } from "@/lib/types";
import { CopyButton } from "./CopyButton";

export function MessageCopyActions({
  message,
  sessionId,
  messageIndex,
}: {
  message: Message;
  sessionId: string;
  messageIndex: number;
}) {
  const menu = useRef<HTMLDetailsElement>(null);
  const [open, setOpen] = useState(false);
  const options = copyOptions(message.blocks, message.role === "user");
  useEffect(() => {
    if (!open) return;
    function closeOutside(event: PointerEvent) {
      if (menu.current && !menu.current.contains(event.target as Node))
        menu.current.open = false;
    }
    document.addEventListener("pointerdown", closeOutside);
    return () => document.removeEventListener("pointerdown", closeOutside);
  }, [open]);
  if (!options.length) return null;
  const copy = (scope: CopyScope) =>
    resolveCopyText(message.blocks, scope, (index) =>
      api.block(sessionId, `${messageIndex}.${index}`),
    );
  return (
    <div className="message-actions ml-auto flex items-center gap-0.5">
      <CopyButton
        title={options[0].label}
        value={() => copy(options[0].scope)}
      />
      {options.length > 1 && (
        <details
          ref={menu}
          onToggle={(event) => setOpen(event.currentTarget.open)}
          className="relative"
          onBlur={(event) => {
            if (
              !event.currentTarget.contains(event.relatedTarget as Node | null)
            )
              event.currentTarget.open = false;
          }}
          onKeyDown={(event) => {
            if (event.key === "Escape") {
              event.preventDefault();
              event.currentTarget.open = false;
              event.currentTarget.querySelector("summary")?.focus();
            }
          }}
        >
          <summary
            aria-label="More copy options"
            title="More copy options"
            className="flex cursor-pointer list-none items-center rounded-md px-1.5 py-1 text-muted-foreground hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring [&::-webkit-details-marker]:hidden"
          >
            <ChevronDown size={13} />
          </summary>
          <div className="absolute right-0 top-full z-20 mt-1 flex min-w-max flex-col rounded-md border border-border bg-popover p-1 shadow-md">
            {options.slice(1).map((option) => (
              <CopyButton
                key={option.scope}
                label={option.label}
                className="justify-start px-3 py-2"
                value={() => copy(option.scope)}
              />
            ))}
          </div>
        </details>
      )}
    </div>
  );
}
