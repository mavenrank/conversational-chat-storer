import type { SourceId } from "./types";

export const SOURCE_STYLE: Record<SourceId, { label: string; text: string; background: string; rail: string; active: string }> = {
  claude: { label: "Claude", text: "text-claude", background: "bg-claude/15", rail: "bg-claude", active: "bg-claude/25 border-claude/70 ring-1 ring-claude/40" },
  opencode: { label: "OpenCode", text: "text-opencode", background: "bg-opencode/15", rail: "bg-opencode", active: "bg-opencode/25 border-opencode/70 ring-1 ring-opencode/40" },
  gemini: { label: "Gemini", text: "text-gemini", background: "bg-gemini/15", rail: "bg-gemini", active: "bg-gemini/25 border-gemini/70 ring-1 ring-gemini/40" },
  kilocode: { label: "Kilocode", text: "text-kilocode", background: "bg-kilocode/15", rail: "bg-kilocode", active: "bg-kilocode/25 border-kilocode/70 ring-1 ring-kilocode/40" },
  codex: { label: "Codex", text: "text-codex", background: "bg-codex/15", rail: "bg-codex", active: "bg-codex/25 border-codex/70 ring-1 ring-codex/40" },
};
