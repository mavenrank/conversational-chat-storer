/**
 * Turning blocks back into text, for the clipboard and for reading.
 *
 * The old header button copied `message.text`, which is prose only — every tool
 * call and every reasoning block was dropped. Worse, `text` was a plain pydantic
 * `@property`, so it never reached the client at all and the button pasted
 * "undefined".
 *
 * Three scopes, because they answer different questions:
 *
 *   answer  — just what the model said. What you paste into a doc.
 *   tools   — the searches and commands with their results, then the answer.
 *             What you paste when someone asks "where did that come from".
 *   full    — thinking, then tools, then the answer, in the order they happened.
 *             The whole turn.
 */

import type { Block, ToolDetail } from "./types";

export type CopyScope = "answer" | "tools" | "full";

/** Only offer scopes that add content beyond the preceding option. */
export function copyOptions(blocks: Block[], isUser = false) {
  const options: { scope: CopyScope; label: string }[] = [];
  const prose = blocks.some((block) => block.kind === "text");
  const tools = blocks.some((block) => block.kind === "tool_use");
  const thinking = blocks.some((block) => block.kind === "thinking");
  if (prose)
    options.push({
      scope: "answer",
      label: isUser ? "Copy message" : "Copy reply",
    });
  if (tools)
    options.push({
      scope: "tools",
      label: prose ? "Copy reply with tools" : "Copy tools",
    });
  if (thinking)
    options.push({
      scope: "full",
      label: prose || tools ? "Copy everything" : "Copy reasoning",
    });
  return options;
}

/** Resolve only the collapsed blocks included in the chosen scope. */
export async function resolveCopyText(
  blocks: Block[],
  scope: CopyScope,
  load: (index: number) => Promise<Block>,
): Promise<string> {
  const resolved = [...blocks];
  const pending = blocks.flatMap((block, index) => {
    const needed =
      block.kind === "thinking"
        ? scope === "full" && block.elided
        : block.kind === "tool_use" &&
          scope !== "answer" &&
          block.detail.elided;
    return needed ? [index] : [];
  });
  for (let offset = 0; offset < pending.length; offset += 4) {
    await Promise.all(
      pending.slice(offset, offset + 4).map(async (index) => {
        resolved[index] = await load(index);
      }),
    );
  }
  return blocksToText(resolved, scope);
}

export function blocksToText(blocks: Block[], scope: CopyScope): string {
  const sections: string[] = [];

  for (const block of blocks) {
    if (block.kind === "text") {
      sections.push(block.text.trim());
      continue;
    }

    if (block.kind === "thinking") {
      if (scope !== "full") continue;
      const label = block.subject ? `Thinking — ${block.subject}` : "Thinking";
      // Elided blocks have empty text until expanded; say so rather than
      // emitting an empty heading.
      const body = block.text.trim() || "(collapsed — expand to load)";
      sections.push(`${label}:\n${indent(body)}`);
      continue;
    }

    if (scope === "answer") continue;
    sections.push(toolToText(block));
  }

  return sections.filter(Boolean).join("\n\n");
}

/** One tool call as `Name: query` followed by its indented result. */
export function toolToText(
  block: Extract<Block, { kind: "tool_use" }>,
): string {
  const detail = block.detail;
  const head = toolHeadline(block.name, detail);
  const body = toolBody(detail);
  const status = block.status === "error" ? " [error]" : "";
  return body ? `${head}${status}:\n${indent(body)}` : `${head}${status}`;
}

function toolHeadline(name: string, detail: ToolDetail): string {
  switch (detail.category) {
    case "file_read":
      return `Read ${detail.path}`;
    case "file_write":
      return `Write ${detail.path}`;
    case "file_edit":
      return `Edit ${detail.path}`;
    case "command":
      return `$ ${detail.command}`;
    case "search":
      return `${name}: ${detail.query}`;
    case "subagent":
      return `Subagent (${detail.agent_type}): ${detail.description}`;
    default:
      return name;
  }
}

function toolBody(detail: ToolDetail): string {
  switch (detail.category) {
    case "file_read":
    case "file_write":
      return detail.elided ? "(collapsed — expand to load)" : detail.content;
    case "file_edit":
      return detail.unified_diff || joinDiff(detail.old_text, detail.new_text);
    case "command":
    case "search":
      return detail.elided ? "(collapsed — expand to load)" : detail.output;
    case "generic":
      return [
        Object.keys(detail.input).length
          ? `Input:\n${JSON.stringify(detail.input, null, 2)}`
          : "",
        detail.elided ? "(collapsed — expand to load)" : detail.output,
      ]
        .filter(Boolean)
        .join("\n\n");
    case "subagent":
      return detail.result;
    default:
      return "";
  }
}

function joinDiff(oldText: string, newText: string): string {
  const lines = [
    ...oldText
      .split("\n")
      .filter(Boolean)
      .map((l) => `-${l}`),
    ...newText
      .split("\n")
      .filter(Boolean)
      .map((l) => `+${l}`),
  ];
  return lines.join("\n");
}

function indent(text: string): string {
  return text
    .split("\n")
    .map((line) => (line.trim() ? `  ${line}` : line))
    .join("\n");
}
