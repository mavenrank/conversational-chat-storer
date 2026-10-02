import { useMemo, type ReactNode } from "react";

/**
 * Minimal markdown renderer.
 *
 * Deliberately hand-rolled rather than pulling in a parser: transcripts only
 * use fenced code, inline code, headings, lists, bold/italic and links, and a
 * full markdown pipeline plus a highlighter is a large dependency to ship for
 * that. Everything is emitted as React nodes, so no HTML is ever injected.
 */
export function Markdown({ text }: { text: string }) {
  const blocks = useMemo(() => parse(text), [text]);
  return <div className="space-y-3.5">{blocks}</div>;
}

function parse(text: string): ReactNode[] {
  const out: ReactNode[] = [];
  const lines = text.replace(/\r\n?/g, "\n").split("\n");
  let index = 0;
  let key = 0;

  while (index < lines.length) {
    const line = lines[index];

    if (line.trimStart().startsWith("```")) {
      const language = line.trim().slice(3).trim();
      const body: string[] = [];
      index++;
      while (
        index < lines.length &&
        !lines[index].trimStart().startsWith("```")
      ) {
        body.push(lines[index]);
        index++;
      }
      index++;
      out.push(
        <pre
          key={key++}
          className="overflow-x-auto rounded-md border border-border bg-background/70 p-3.5 font-sans text-xs leading-[1.7] text-foreground/75"
        >
          {language && (
            <div className="mb-1.5 text-[11px] uppercase tracking-wider text-muted-foreground">
              {language}
            </div>
          )}
          <code>{body.join("\n")}</code>
        </pre>,
      );
      continue;
    }

    // GFM tables: a header row, a |---|---| delimiter, then body rows.
    if (line.includes("|") && isDelimiterRow(lines[index + 1] ?? "")) {
      const header = splitRow(line);
      const rows: string[][] = [];
      index += 2;
      while (
        index < lines.length &&
        lines[index].includes("|") &&
        lines[index].trim()
      ) {
        rows.push(splitRow(lines[index]));
        index++;
      }
      out.push(
        <div
          key={key++}
          className="markdown-table-scroll"
          role="region"
          aria-label="Table"
          tabIndex={0}
        >
          <table
            className="markdown-table"
            style={{ minWidth: `${header.length * 10}rem` }}
          >
            <thead>
              <tr>
                {header.map((cell, i) => (
                  <th key={i} scope="col">
                    {inline(cell)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, r) => (
                <tr key={r}>
                  {header.map((_, c) => (
                    <td key={c}>{inline(row[c] ?? "")}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      continue;
    }

    // Blockquotes.
    if (/^\s*>\s?/.test(line)) {
      const quoted: string[] = [];
      while (index < lines.length && /^\s*>\s?/.test(lines[index])) {
        quoted.push(lines[index].replace(/^\s*>\s?/, ""));
        index++;
      }
      out.push(
        <blockquote
          key={key++}
          className="border-l-2 border-border pl-4 text-foreground/70"
        >
          {inline(quoted.join("\n"))}
        </blockquote>,
      );
      continue;
    }

    // Horizontal rule.
    if (/^\s*([-*_])\1{2,}\s*$/.test(line)) {
      out.push(<hr key={key++} className="border-border" />);
      index++;
      continue;
    }

    const heading = /^(#{1,6})\s+(.*)$/.exec(line);
    if (heading) {
      const level = heading[1].length;
      out.push(
        <div
          key={key++}
          className={
            level <= 2
              ? "mt-2 text-[15px] font-semibold text-foreground"
              : "mt-1.5 text-[15px] font-semibold text-foreground/75"
          }
        >
          {inline(heading[2])}
        </div>,
      );
      index++;
      continue;
    }

    if (/^\s*([-*+]|\d+\.)\s+/.test(line)) {
      const items: string[] = [];
      while (
        index < lines.length &&
        /^\s*([-*+]|\d+\.)\s+/.test(lines[index])
      ) {
        items.push(lines[index].replace(/^\s*([-*+]|\d+\.)\s+/, ""));
        index++;
      }
      out.push(
        <ul
          key={key++}
          className="ml-5 list-disc space-y-1.5 marker:text-muted-foreground"
        >
          {items.map((item, i) => (
            <li key={i}>{inline(item)}</li>
          ))}
        </ul>,
      );
      continue;
    }

    if (!line.trim()) {
      index++;
      continue;
    }

    const paragraph: string[] = [];
    while (
      index < lines.length &&
      lines[index].trim() &&
      !lines[index].trimStart().startsWith("```") &&
      !/^#{1,6}\s/.test(lines[index]) &&
      !/^\s*([-*+]|\d+\.)\s+/.test(lines[index]) &&
      !/^\s*>\s?/.test(lines[index]) &&
      !(lines[index].includes("|") && isDelimiterRow(lines[index + 1] ?? ""))
    ) {
      paragraph.push(lines[index]);
      index++;
    }
    // A line can look like a block opener without matching its full grammar
    // (for example a heading containing a Unicode line separator). Always
    // consume it, otherwise this loop allocates paragraphs until the tab dies.
    if (paragraph.length === 0) {
      paragraph.push(line);
      index++;
    }
    out.push(
      <p key={key++} className="whitespace-pre-wrap">
        {inline(paragraph.join("\n"))}
      </p>,
    );
  }

  return out;
}

/** `|---|:--:|---|` — the row that turns the line above it into a table header. */
function isDelimiterRow(line: string): boolean {
  if (!line.includes("|") || !line.includes("-")) return false;
  return splitRow(line).every((cell) => /^:?-{2,}:?$/.test(cell.trim()));
}

function splitRow(line: string): string[] {
  return line
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cell) => cell.trim());
}

/** Inline code, bold, italic and links. */
function inline(text: string): ReactNode[] {
  const pattern =
    /(`[^`]+`)|(\*\*[^*]+\*\*)|(\*[^*\n]+\*)|(\[[^\]]+\]\([^)]+\))/g;
  const out: ReactNode[] = [];
  let last = 0;
  let key = 0;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > last) out.push(text.slice(last, match.index));
    const token = match[0];

    if (token.startsWith("`")) {
      out.push(
        <code
          key={key++}
          className="rounded-sm bg-accent px-1 py-[1px] font-sans text-[0.9em] text-read"
        >
          {token.slice(1, -1)}
        </code>,
      );
    } else if (token.startsWith("**")) {
      out.push(
        <strong key={key++} className="font-semibold">
          {token.slice(2, -2)}
        </strong>,
      );
    } else if (token.startsWith("[")) {
      const link = /\[([^\]]+)\]\(([^)]+)\)/.exec(token);
      out.push(
        <a
          key={key++}
          href={link?.[2]}
          target="_blank"
          rel="noreferrer noopener"
          className="text-user underline underline-offset-2 hover:text-read"
        >
          {link?.[1]}
        </a>,
      );
    } else {
      out.push(
        <em key={key++} className="italic">
          {token.slice(1, -1)}
        </em>,
      );
    }
    last = match.index + token.length;
  }

  if (last < text.length) out.push(text.slice(last));
  return out;
}
