"""Strip prompt scaffolding out of tool output.

Search tools (TinySearch and friends) do not return their results — they return
an entire *prompt* wrapping those results: instruction preamble, banner rules,
per-result title/URL/preview/chunk headers, then the question and today's date
repeated at the end. One observed response was 8 KB of which perhaps 1.5 KB was
information.

That scaffolding is written to disk, sent over the wire, re-rendered on every
scroll, and pasted into the clipboard when the row is copied. It is also
identical between calls, so it compresses to nothing useful and helps nobody.

This module reduces such payloads to the part with content: the results, as a
compact numbered list of ``title / url / text``. Applied at parse time, so the
saving lands in the archive, the API response, the UI and the markdown export
at once rather than being patched at each.

Nothing is discarded that carries information. If a payload does not match the
known scaffolding shape it is returned unchanged — a trimmer that silently eats
unfamiliar output is worse than no trimmer.
"""

from __future__ import annotations

import json
import re

#: The banner rule these prompts use to separate sections. Long runs of '=' are
#: the giveaway that a payload is a prompt rather than a result.
_RULE = re.compile(r"^={20,}$", re.MULTILINE)

#: Section headers, e.g. "RESULT 3", "TITLE 1", "URL 1".
_SECTION = re.compile(r"^(RESULT|TITLE|URL|SEARCH PREVIEW|RELEVANT TEXT)\s*(\d+)?$")

#: Chunk separators inside RELEVANT TEXT: "----- RELEVANT CHUNK 2 -----".
_CHUNK = re.compile(r"^-{3,}\s*RELEVANT CHUNK\s*\d+\s*-{3,}$", re.MULTILINE)

#: Header sections that are instructions, not content.
_DROP_SECTIONS = {
    "SEARCH-GROUNDED ANSWER PROMPT",
    "CRITICAL INSTRUCTIONS",
    "QUESTION",
    "TODAY",
    "RESULTS",
}

#: Below this there is nothing worth trimming.
_MIN_LENGTH = 400


def looks_like_search_prompt(text: str) -> bool:
    """True when a payload is prompt scaffolding rather than plain output."""
    if len(text) < _MIN_LENGTH:
        return False
    return "SEARCH-GROUNDED ANSWER PROMPT" in text or (
        len(_RULE.findall(text)) >= 4 and "RESULT 1" in text
    )


def trim_search_output(text: str) -> str:
    """Reduce a search prompt to its results.

    Returns the original text when the shape is not recognised.
    """
    if not looks_like_search_prompt(text):
        return text

    results = _extract_results(text)
    if not results:
        return text

    lines: list[str] = []
    for index, result in enumerate(results, start=1):
        title = result.get("title", "").strip()
        url = result.get("url", "").strip()
        body = result.get("text", "").strip()

        header = f"{index}. {title}" if title else f"{index}."
        lines.append(header)
        if url:
            lines.append(f"   {url}")
        if body:
            for line in body.splitlines():
                stripped = line.strip()
                if stripped:
                    lines.append(f"   {stripped}")
        lines.append("")

    return "\n".join(lines).rstrip()


def trim_tool_output(text: str) -> str:
    """Trim a tool payload, unwrapping a JSON ``{"answer": ...}`` envelope.

    Search tools often return the whole prompt inside a JSON field, so the
    scaffolding check has to happen after unwrapping.
    """
    if not text or len(text) < _MIN_LENGTH:
        return text

    stripped = text.lstrip()
    if stripped.startswith("{"):
        try:
            payload = json.loads(text)
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            for key in ("answer", "result", "output", "content"):
                inner = payload.get(key)
                if isinstance(inner, str) and looks_like_search_prompt(inner):
                    return trim_search_output(inner)

    return trim_search_output(text)


def _extract_results(text: str) -> list[dict[str, str]]:
    """Walk the prompt line by line and collect each result's fields.

    Line-based rather than split-on-rule: the format uses banner rules of two
    different widths — long ``=`` runs between top-level sections and short
    six-character ones around field values — so splitting on one width misses
    the other and yields nothing.
    """
    results: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    field: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        nonlocal field, buffer
        if current is not None and field and buffer:
            _assign(current, field, "\n".join(buffer).strip())
        field, buffer = None, []

    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()

        # Any run of '=' is a separator, at either width.
        if stripped and set(stripped) == {"="}:
            continue

        header = _SECTION.match(stripped)
        if header:
            flush()
            name = header.group(1)
            if name == "RESULT":
                if current:
                    results.append(current)
                current = {}
            else:
                field = name
            continue

        if stripped in _DROP_SECTIONS:
            flush()
            field = None
            # Everything until the next recognised header is instruction text.
            current = current if current is not None else None
            continue

        if field and current is not None:
            buffer.append(line)

    flush()
    if current:
        results.append(current)

    return [r for r in results if r.get("url") or r.get("text")]


def _assign(result: dict[str, str], section: str, body: str) -> None:
    if section == "TITLE":
        result.setdefault("title", body)
    elif section == "URL":
        result.setdefault("url", body)
    elif section == "RELEVANT TEXT":
        # Chunk markers are structural noise; the chunks themselves are content.
        result["text"] = _CHUNK.sub("", body).strip()
    elif section == "SEARCH PREVIEW":
        # Only useful when no fuller text follows.
        result.setdefault("text", body)
