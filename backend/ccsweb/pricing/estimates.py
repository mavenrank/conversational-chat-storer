"""Offline API equivalents. Read request usage, never price a cumulative context tier."""

from __future__ import annotations

import json
from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path

from ccsweb.models import SessionDetail, Usage
from ccsweb.models.session import CostEstimate
from ccsweb.sources.codex import _usage
from ccsweb.util.jsonio import iter_jsonl


@lru_cache(maxsize=1)
def rates() -> dict:
    return json.loads(Path(__file__).with_name("verified_rates.json").read_text(encoding="utf-8"))


def price_request(model: str | None, provider: str | None, usage: Usage) -> float | None:
    book = rates()
    key = book["aliases"].get(model, model)
    rate = book["models"].get(key)
    if not rate or (provider and provider != rate["provider"]):
        return None
    amounts = (
        (usage.input_tokens, rate["input"]),
        (usage.cached_tokens, rate["cache_read"]),
        (usage.cache_write_tokens, rate["cache_write"]),
        (usage.cache_write_1h_tokens, rate["cache_write_1h"]),
    )
    if any(count > 0 and value is None for count, value in amounts):
        return None
    threshold = rate["long_context_threshold"]
    long = bool(threshold and usage.context_tokens > threshold)
    inputs = sum(count * (value or 0) for count, value in amounts)
    output = usage.generated_tokens * rate["output"]
    if long:
        inputs *= rate["long_input_multiplier"]
        output *= rate["long_output_multiplier"]
    return (inputs + output) / 1_000_000


def estimate(requests: Iterable[tuple[str | None, str | None, Usage]]) -> CostEstimate:
    result = CostEstimate(rates_verified_at=rates()["verified_at"])
    total = 0.0
    unknown = set()
    for model, provider, usage in requests:
        if usage.total_tokens == 0:
            continue
        cost = price_request(model, provider, usage)
        if cost is None:
            result.unpriced_requests += 1
            unknown.add(model or "Unknown model")
        else:
            result.priced_requests += 1
            total += cost
    result.estimated_usd = round(total, 6) if result.priced_requests else None
    result.unpriced_models = sorted(unknown)
    result.complete = bool(result.priced_requests and not result.unpriced_requests)
    return result


def transcript_requests(session: SessionDetail) -> Iterable[tuple[str | None, str | None, Usage]]:
    # Claude repeats one response's usage across split assistant records.
    requests = {}
    default = {"claude": "anthropic", "gemini": "google"}.get(session.source)
    for message in session.messages:
        if message.usage and message.role == "assistant":
            requests[message.request_id or message.id] = (
                message.model,
                message.provider or default,
                message.usage,
            )
    return requests.values()


def codex_requests(path: Path) -> Iterable[tuple[str | None, str | None, Usage]]:
    return codex_record_requests(iter_jsonl(path))


def codex_record_requests(
    records: Iterable[dict],
) -> Iterable[tuple[str | None, str | None, Usage]]:
    """Keep only usage tuples; modern ledgers supersede legacy events per turn."""
    model = None
    provider = "openai"
    turn = "legacy"
    modern = []
    legacy = []
    modern_turns = set()
    seen = set()
    previous = {}
    for record in records:
        kind = record.get("type")
        payload = record.get("payload") or {}
        turn = str(payload.get("turn_id") or turn)
        if kind == "session_meta":
            model = payload.get("model") or model
            provider = payload.get("model_provider") or provider
        elif kind == "turn_context":
            model = payload.get("model") or model
        elif kind == "token_usage_record":
            modern_turns.add(turn)
            request = payload.get("response_id")
            if request and request in seen:
                continue
            if request:
                seen.add(request)
            raw = payload.get("usage")
            if isinstance(raw, dict):
                modern.append((model, provider, _usage(raw)))
        elif payload.get("type") == "token_count":
            total = (payload.get("info") or {}).get("total_token_usage")
            if isinstance(total, dict):
                reset = any(v < previous.get(k, 0) for k, v in total.items() if isinstance(v, int))
                delta = {
                    k: max(0, v - (0 if reset else previous.get(k, 0)))
                    for k, v in total.items()
                    if isinstance(v, int)
                }
                previous = total
                legacy.append((turn, model, provider, _usage(delta)))
    return [*modern, *((m, p, u) for t, m, p, u in legacy if t not in modern_turns)]
