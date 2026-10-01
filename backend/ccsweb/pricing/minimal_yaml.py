"""A very small YAML reader for ``pricing.yaml``.

PyYAML is the right tool and is used when installed. This fallback exists so a
missing optional dependency degrades to "prices still work" instead of "no
pricing at all", and so the pricing tests run without any third-party package.

It supports only what ``pricing.yaml`` actually uses: nested mappings by
indentation, inline ``{a: 1, b: 2}`` flow mappings, scalars, and ``#`` comments.
It is not a general YAML parser and should not be used for anything else.
"""

from __future__ import annotations

from typing import Any


def parse(text: str) -> dict[str, Any]:
    root: dict[str, Any] = {}
    # Stack of (indent, container) so a dedent pops back to the right parent.
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]
    pending_key: str | None = None
    pending_indent = 0

    for raw_line in text.splitlines():
        line = _strip_comment(raw_line)
        if not line.strip():
            continue

        indent = len(line) - len(line.lstrip())
        content = line.strip()
        if ":" not in content:
            continue

        key, _, value = content.partition(":")
        key = key.strip()
        value = value.strip()

        # A key with no value opened a block last iteration; create it lazily so
        # empty blocks do not leave stray dicts behind.
        if pending_key is not None and indent > pending_indent:
            parent = stack[-1][1]
            child: dict[str, Any] = {}
            parent[pending_key] = child
            stack.append((pending_indent, child))
            pending_key = None

        while stack and indent <= stack[-1][0]:
            stack.pop()
        if not stack:
            stack = [(-1, root)]

        container = stack[-1][1]

        if not value:
            pending_key = key
            pending_indent = indent
            continue

        container[key] = _flow(value) if value.startswith("{") else _scalar(value)
        pending_key = None

    return root


def _strip_comment(line: str) -> str:
    """Remove a trailing comment, ignoring '#' inside quotes."""
    out = []
    quote: str | None = None
    for char in line:
        if quote:
            if char == quote:
                quote = None
        elif char in "'\"":
            quote = char
        elif char == "#":
            break
        out.append(char)
    return "".join(out).rstrip()


def _flow(text: str) -> dict[str, Any]:
    """Parse ``{ a: 1, b: 2 }``."""
    inner = text.strip().lstrip("{").rstrip("}")
    result: dict[str, Any] = {}
    for part in inner.split(","):
        if ":" not in part:
            continue
        key, _, value = part.partition(":")
        result[key.strip()] = _scalar(value.strip())
    return result


def _scalar(text: str) -> Any:
    text = text.strip().strip("'\"")
    lowered = text.lower()
    if lowered in {"true", "yes"}:
        return True
    if lowered in {"false", "no"}:
        return False
    if lowered in {"null", "~", ""}:
        return None
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        return text
