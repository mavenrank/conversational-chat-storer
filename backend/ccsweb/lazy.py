"""Eliding heavy payloads so transcripts load fast.

A single opencode session can hold megabytes of file reads and command output.
Sending all of it just to render collapsed accordions is wasteful, so the
session endpoint blanks the bulky fields and records their size. The client
fetches the real content per block when the user expands one.

Block addressing is positional and stable for a given transcript:
``<message_index>.<block_index>``. Positions are derived from the same ordered
read on both requests, so no ids need to be persisted anywhere.
"""

from __future__ import annotations

from ccsweb.models import Block, SessionDetail
from ccsweb.models.blocks import Heavy

#: Fields that hold the bulk of a payload, by detail category.
#:
#: ``file_edit`` carries ``unified_diff`` because a "new file" edit embeds the
#: entire file as one large diff; ``old_text``/``new_text`` are left inline so a
#: collapsed row can still show its +/- counts without a round trip.
_HEAVY_FIELDS = {
    "file_read": "content",
    "file_write": "content",
    "file_edit": "unified_diff",
    "command": "output",
    "search": "output",
    "subagent": "result",
    "generic": "output",
}


def block_ref(message_index: int, block_index: int) -> str:
    return f"{message_index}.{block_index}"


def parse_block_ref(ref: str) -> tuple[int, int] | None:
    head, _, tail = ref.partition(".")
    if not head.isdigit() or not tail.isdigit():
        return None
    return int(head), int(tail)


def locate_block(session: SessionDetail, ref: str) -> Block | None:
    """Resolve a ``m.b`` reference against a freshly loaded transcript."""
    position = parse_block_ref(ref)
    if position is None:
        return None
    message_index, block_index = position
    if not 0 <= message_index < len(session.messages):
        return None
    blocks = session.messages[message_index].blocks
    if not 0 <= block_index < len(blocks):
        return None
    return blocks[block_index]


def elide_session(session: SessionDetail, threshold: int) -> SessionDetail:
    """Return the session with heavy payloads stripped.

    Mutates in place and returns the same object; callers always own a
    freshly-parsed instance.
    """
    for message in session.messages:
        for block in message.blocks:
            if block.kind == "thinking":
                # Thinking bodies are collapsed by default in the UI. Keep the
                # subject, which is the accordion label.
                _elide_thinking(block, threshold)
            elif block.kind == "tool_use":
                _elide_tool(block, threshold)
    return session


def _elide_thinking(block, threshold: int) -> None:
    size = len(block.text.encode("utf-8"))
    if size >= threshold:
        block.text = ""
        block.elided = True
    block.size_bytes = size


def _elide_tool(block, threshold: int) -> None:
    detail = block.detail
    if not isinstance(detail, Heavy):
        return
    field = _HEAVY_FIELDS.get(detail.category)
    if field is None:
        return
    value = getattr(detail, field, "") or ""
    size = len(value.encode("utf-8"))
    detail.size_bytes = size
    if size >= threshold:
        setattr(detail, field, "")
        detail.elided = True
