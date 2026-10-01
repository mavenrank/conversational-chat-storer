"""Price a session's token usage.

Rates live in ``pricing.yaml`` next to this module — edit that, not this file.

Two things this deliberately does *not* do:

* It never guesses. A model with no entry is reported as unpriced and its tokens
  are excluded from the total, so a gap in the table is visible rather than
  silently costing $0.
* It never conflates providers. OpenCode Go and Zen publish different rates for
  the same model ids — DeepSeek V4 Pro is $0.435/1M input on Go against $1.74 on
  Zen — so pricing keys on ``(provider, model)``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from ccsweb.models import Usage

PRICING_FILE = Path(__file__).with_name("pricing.yaml")


@dataclass
class Rate:
    """USD per 1M tokens for one model on one provider."""

    input: float = 0.0
    output: float = 0.0
    cache_read: float = 0.0
    cache_write: float = 0.0

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Rate":
        return cls(
            input=float(raw.get("input") or 0.0),
            output=float(raw.get("output") or 0.0),
            cache_read=float(raw.get("cache_read") or 0.0),
            cache_write=float(raw.get("cache_write") or 0.0),
        )


@dataclass
class Priced:
    """Cost breakdown for one usage record."""

    input_cost: float = 0.0
    output_cost: float = 0.0
    cache_read_cost: float = 0.0
    total: float = 0.0
    #: True when the provider bills a flat subscription, so this is "what it
    #: would have cost on the API" rather than money actually charged.
    notional: bool = False
    #: Set when no rate was found; the tokens are then excluded from the total.
    unpriced_model: str | None = None


@dataclass
class PriceBook:
    providers: dict[str, dict[str, Rate]] = field(default_factory=dict)
    notional: set[str] = field(default_factory=set)
    display_names: dict[str, str] = field(default_factory=dict)
    aliases: dict[str, str] = field(default_factory=dict)

    def rate(self, provider: str | None, model: str | None) -> tuple[Rate | None, bool]:
        """Look up a rate. Returns ``(rate, notional)``; rate is ``None`` if unknown."""
        if not model:
            return None, False
        key = self.aliases.get(model, model)

        # Exact provider match first — Go and Zen genuinely differ.
        if provider and provider in self.providers:
            found = self.providers[provider].get(key)
            if found is not None:
                return found, provider in self.notional

        # Otherwise take the first provider that lists the model. Better an
        # approximate figure than none, and the UI labels totals as estimates.
        for name, models in self.providers.items():
            if key in models:
                return models[key], name in self.notional

        return None, False


@lru_cache(maxsize=1)
def load_price_book(path: Path | None = None) -> PriceBook:
    """Parse pricing.yaml.

    Uses PyYAML when available and falls back to a tiny parser otherwise, so
    pricing works without adding a dependency for one static file.
    """
    target = path or PRICING_FILE
    try:
        text = target.read_text(encoding="utf-8")
    except OSError:
        return PriceBook()

    try:
        import yaml  # type: ignore

        raw = yaml.safe_load(text) or {}
    except ImportError:  # pragma: no cover - exercised only without PyYAML
        from ccsweb.pricing.minimal_yaml import parse

        raw = parse(text)

    book = PriceBook(aliases=dict(raw.get("aliases") or {}))
    for name, block in (raw.get("providers") or {}).items():
        if not isinstance(block, dict):
            continue
        if block.get("notional"):
            book.notional.add(name)
        book.display_names[name] = str(block.get("display_name") or name)
        models: dict[str, Rate] = {}
        for model, rates in (block.get("models") or {}).items():
            if isinstance(rates, dict):
                models[model] = Rate.from_dict(rates)
        book.providers[name] = models
    return book


def price_usage(
    usage: Usage,
    model: str | None,
    provider: str | None = None,
    book: PriceBook | None = None,
) -> Priced:
    """Cost one usage record.

    ``cache_write`` is not applied: none of the sources report cache-write
    tokens separately, so charging for them would be invention. Claude's
    ``cache_creation_input_tokens`` is folded into ``cached_tokens`` upstream and
    is therefore priced at the cheaper read rate — a slight under-estimate,
    preferred over a fabricated one.
    """
    book = book or load_price_book()
    rate, notional = book.rate(provider, model)
    if rate is None:
        return Priced(unpriced_model=model or "unknown")

    million = 1_000_000
    input_cost = usage.input_tokens / million * rate.input
    # Thinking tokens are billed as output by every provider here.
    output_cost = (usage.output_tokens + usage.thinking_tokens) / million * rate.output
    cache_cost = usage.cached_tokens / million * rate.cache_read

    return Priced(
        input_cost=input_cost,
        output_cost=output_cost,
        cache_read_cost=cache_cost,
        total=input_cost + output_cost + cache_cost,
        notional=notional,
    )
