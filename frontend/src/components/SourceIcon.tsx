import claude from "@lobehub/icons-static-svg/icons/claude.svg";
import openai from "@lobehub/icons-static-svg/icons/openai.svg";
import opencode from "@lobehub/icons-static-svg/icons/opencode.svg";
import gemini from "@lobehub/icons-static-svg/icons/gemini.svg";
import kilocode from "@lobehub/icons-static-svg/icons/kilocode.svg";
import type { SourceId } from "@/lib/types";
import { cn } from "@/lib/utils";

const LOGOS: Record<SourceId, string> = { claude, codex: openai, opencode, gemini, kilocode };

export function SourceIcon({ source, className }: { source: SourceId; className?: string }) {
  const mask = `url("${LOGOS[source]}")`;
  return <span aria-hidden="true" className={cn("inline-block h-4 w-4 shrink-0 bg-current", className)}
    style={{ maskImage: mask, WebkitMaskImage: mask, maskSize: "contain", WebkitMaskSize: "contain", maskPosition: "center", WebkitMaskPosition: "center", maskRepeat: "no-repeat", WebkitMaskRepeat: "no-repeat" }} />;
}
