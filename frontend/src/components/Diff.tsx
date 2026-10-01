import { useMemo } from "react";
import { cn } from "@/lib/utils";

type Line = { kind: "add" | "del" | "ctx" | "hunk"; text: string };

/**
 * Renders either a ready-made unified diff (kilocode supplies one) or an
 * old/new pair (opencode and Gemini), so both source shapes land here.
 *
 * Gutter markers are separated from the content so the code column stays
 * aligned regardless of +/- prefixes.
 */
export function Diff({
  unified,
  oldText,
  newText,
}: {
  unified?: string;
  oldText?: string;
  newText?: string;
}) {
  const lines = useMemo<Line[]>(() => {
    if (unified && unified.trim()) return parseUnified(unified);
    return fromPair(oldText ?? "", newText ?? "");
  }, [unified, oldText, newText]);

  const added = lines.filter((l) => l.kind === "add").length;
  const removed = lines.filter((l) => l.kind === "del").length;

  return (
    <div>
      <div className="flex gap-3 border-b border-border px-3 py-1 text-xs tabular-nums">
        <span className="text-add">+{added}</span>
        <span className="text-destructive">−{removed}</span>
      </div>
      <div className="max-h-[26rem] overflow-auto text-xs leading-[1.55]">
        {lines.map((line, index) => (
          <div
            key={index}
            className={cn(
              "flex whitespace-pre",
              line.kind === "add" && "bg-add/[0.08]",
              line.kind === "del" && "bg-del/[0.08]",
              line.kind === "hunk" && "bg-accent",
            )}
          >
            <span
              className={cn(
                "w-5 shrink-0 select-none pl-2 text-center",
                line.kind === "add" && "text-add",
                line.kind === "del" && "text-destructive",
                line.kind !== "add" && line.kind !== "del" && "text-muted-foreground",
              )}
            >
              {line.kind === "add" ? "+" : line.kind === "del" ? "−" : " "}
            </span>
            <span
              className={cn(
                "pr-3",
                line.kind === "add" && "text-add",
                line.kind === "del" && "text-destructive",
                line.kind === "hunk" && "text-muted-foreground",
                line.kind === "ctx" && "text-foreground/75",
              )}
            >
              {line.text || " "}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function parseUnified(diff: string): Line[] {
  return diff.split("\n").map((raw): Line => {
    if (raw.startsWith("@@")) return { kind: "hunk", text: raw };
    // File headers must not read as additions or deletions.
    if (raw.startsWith("+++") || raw.startsWith("---") || raw.startsWith("===")) {
      return { kind: "hunk", text: raw };
    }
    if (raw.startsWith("+")) return { kind: "add", text: raw.slice(1) };
    if (raw.startsWith("-")) return { kind: "del", text: raw.slice(1) };
    return { kind: "ctx", text: raw.startsWith(" ") ? raw.slice(1) : raw };
  });
}

function fromPair(oldText: string, newText: string): Line[] {
  const lines: Line[] = [];
  if (oldText) for (const l of oldText.split("\n")) lines.push({ kind: "del", text: l });
  if (newText) for (const l of newText.split("\n")) lines.push({ kind: "add", text: l });
  return lines;
}
