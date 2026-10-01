"""Cached model pricing.

Modelly is the source of truth, but it only answers while its desktop app is
open. So every model we look up is written to a JSON cache, and the cache is
what pricing actually reads. The API is contacted only to fill gaps or on an
explicit refresh.

Resolution order for any (provider, model):

1. the JSON cache — works offline, no network on the hot path
2. Modelly's API — consulted for models the cache has never seen
3. ``pricing.yaml`` — the hand-maintained fallback, so a cold cache with Modelly
   closed still produces figures rather than blanks

Models that resolve nowhere are reported by name rather than priced at zero, so
a gap is visible instead of silently deflating the total.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ccsweb.models import Usage
from ccsweb.pricing.modelly import (
    NANO_PER_USD,
    TOKENS_PER_UNIT,
    ModellyClient,
    ModellyUnavailable,
    ModelPricing,
    Tier,
)

CACHE_VERSION = 1

#: Maps the provider ids our adapters record onto Modelly plan ids, in
#: preference order. OpenCode records ``providerID`` per message, which is
#: exactly the distinction that matters: Go and Zen price the same models
#: differently.
PROVIDER_TO_PLANS: dict[str, list[str]] = {
    "opencode-go": ["opencode-go"],
    "opencode": ["opencode-zen-paygo", "opencode-zen", "opencode"],
    "github-copilot": ["github-copilot", "anthropic-direct"],
    "anthropic": ["anthropic-direct", "anthropic"],
    "google": ["google-direct", "google", "gemini"],
    "openai": ["openai-direct", "openai"],
}


@dataclass
class CostBreakdown:
    """What one usage record cost, and on what basis."""

    input_usd: float = 0.0
    output_usd: float = 0.0
    cached_usd: float = 0.0
    total_usd: float = 0.0

    model: str = ""
    plan_id: str = ""
    plan_name: str = ""
    #: Where the rates came from: "modelly", "cache", "inferred-free" or
    #: "unpriced".
    basis: str = "unpriced"
    #: True when the seller bills a flat subscription, so this is a notional
    #: "what it would have cost on the API" figure, not money charged.
    notional: bool = False

    #: The session's date — the moment we are trying to price.
    as_of: str | None = None
    #: When the rate used was first observed. If this is *after* ``as_of``, the
    #: rate is being applied to a period it was never verified for.
    rate_observed_at: str | None = None
    #: True when ``as_of`` predates everything Modelly has recorded, so today's
    #: rate is being assumed to have held then. The single largest source of
    #: error in a historical total, and the reason it is surfaced rather than
    #: buried.
    assumed_current_rate: bool = False


class PricingCatalog:
    """Cache-first pricing, backed by Modelly."""

    def __init__(
        self,
        cache_path: Path,
        client: ModellyClient | None = None,
        allow_network: bool = True,
    ) -> None:
        self.cache_path = cache_path
        self.client = client or ModellyClient()
        self.allow_network = allow_network
        self._models: dict[str, ModelPricing] = {}
        self._misses: set[str] = set()
        self._meta: dict[str, Any] = {}
        self._horizon_cache: str | None = None
        self._load()

    # ------------------------------------------------------------------ #
    # Cache I/O
    # ------------------------------------------------------------------ #

    def _load(self) -> None:
        try:
            raw = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if raw.get("version") != CACHE_VERSION:
            return
        self._meta = raw.get("meta") or {}
        for key, value in (raw.get("models") or {}).items():
            if isinstance(value, dict):
                self._models[key] = ModelPricing.from_json(value)

    def save(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": CACHE_VERSION,
            "meta": {
                **self._meta,
                "updated_at": datetime.now(timezone.utc)
                .replace(microsecond=0)
                .isoformat(),
                "note": (
                    "Cached from the Modelly API (127.0.0.1:47113). Prices are "
                    "nano-USD per 1M tokens; null means the tier does not exist, "
                    "0 means free. Refresh with: uv run python -m "
                    "ccsweb.pricing.sync"
                ),
            },
            "models": {k: v.to_json() for k, v in self._models.items()},
        }
        temp = self.cache_path.with_suffix(".json.tmp")
        temp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temp.replace(self.cache_path)

    @property
    def cached_model_count(self) -> int:
        return len(self._models)

    @property
    def updated_at(self) -> str | None:
        return self._meta.get("updated_at")

    # ------------------------------------------------------------------ #
    # Lookup
    # ------------------------------------------------------------------ #

    def lookup(self, model: str) -> tuple[ModelPricing | None, str]:
        """Find a model, returning it with the basis it came from."""
        if not model:
            return None, "unpriced"

        key = model.lower()
        if key in self._models:
            return self._models[key], "cache"
        if key in self._misses or not self.allow_network:
            return None, "unpriced"

        try:
            found = self.client.model(model)
        except ModellyUnavailable:
            # Do not record a miss: Modelly being closed is not evidence that
            # the model is unknown, and caching that would poison the cache.
            return None, "unpriced"

        if found is None:
            self._misses.add(key)
            return None, "unpriced"

        # Index under every alias so the next lookup hits regardless of which
        # identifier the session recorded.
        self._models[key] = found
        for alias in [found.model_id, *found.aliases]:
            if alias:
                self._models[alias.lower()] = found
        return found, "modelly"

    def cost(
        self,
        usage: Usage,
        model: str,
        provider: str | None = None,
        as_of: str | None = None,
    ) -> CostBreakdown:
        """Price one usage record as of the date it happened.

        ``as_of`` should be the session's timestamp. Prices move: a model that
        is $0.30/M today may have been $0.60 in April, and a free promo that
        ran in spring may have ended before a session that used it. Pricing
        historical usage at today's rates is an assumption, and this records
        whether that assumption is being made.

        Modelly answers ``as_of`` properly through its bitemporal schema, but
        only back to when collection started. Before that horizon the honest
        answer is "today's rate, assumed" — flagged via
        ``assumed_current_rate`` — not a confident number.
        """
        pricing, basis = self.lookup(model)
        horizon = self._horizon()
        assumed = bool(as_of and horizon and as_of < horizon)

        if pricing is None and _is_free_variant(model):
            # OpenCode's free promos are named `<model>-free`, consistently
            # across all seven Zen carries. When the catalog has no entry but
            # the name asserts free, take the name at its word — $0.
            #
            # Note what is NOT done here: resolving `<model>-free` to `<model>`
            # and using that price. The suffix is the meaningful part —
            # `deepseek-v4-flash` is $0.14/M while `deepseek-v4-flash-free` is
            # $0 — so stripping it would bill free tokens at the paid rate.
            #
            # Flagged `inferred-free` rather than `cache`/`modelly` so the UI
            # can mark it as a guess from a naming convention, not a source.
            #
            # The inference is about *now*. Free promos are all "limited time",
            # so a session that ran before the promo started — or after it
            # ended — was not necessarily free. `assumed_current_rate` carries
            # that caveat rather than dropping it.
            return CostBreakdown(
                model=model,
                basis="inferred-free",
                as_of=as_of,
                assumed_current_rate=assumed or horizon is None,
            )

        if pricing is None:
            return CostBreakdown(
                model=model or "unknown", basis="unpriced", as_of=as_of
            )

        hints = PROVIDER_TO_PLANS.get(provider or "", [])
        seller = pricing.seller_for([*hints, provider or ""])
        if seller is None:
            return CostBreakdown(model=model, basis="unpriced")

        # Tier is chosen by the prompt size, since long-context bands can
        # double the rate.
        tier = seller.tier_for(usage.input_tokens + usage.cached_tokens)
        if tier is None:
            return CostBreakdown(model=model, basis="unpriced")

        input_usd = _rate(tier.input_nano, usage.input_tokens)
        # Thinking tokens bill as output everywhere we support.
        output_usd = _rate(tier.output_nano, usage.output_tokens + usage.thinking_tokens)
        cached_usd = _rate(tier.cached_read_nano, usage.cached_tokens)

        return CostBreakdown(
            input_usd=input_usd,
            output_usd=output_usd,
            cached_usd=cached_usd,
            total_usd=input_usd + output_usd + cached_usd,
            model=pricing.model_id or model,
            plan_id=seller.plan_id,
            plan_name=seller.plan_name,
            basis=basis,
            as_of=as_of,
            rate_observed_at=seller.valid_from or seller.observed_at,
            assumed_current_rate=assumed,
        )

    def _horizon(self) -> str | None:
        """Earliest date any cached rate was known to hold.

        Anything before this cannot be priced from evidence. Computed from the
        cache so it costs nothing on the hot path.
        """
        if self._horizon_cache is not None:
            return self._horizon_cache or None
        dates = [
            s.valid_from or s.observed_at
            for pricing in self._models.values()
            for s in pricing.sellers
            if s.valid_from or s.observed_at
        ]
        self._horizon_cache = min(dates) if dates else ""
        return self._horizon_cache or None


#: OpenCode names its free promotions `<model>-free`. Seen on all seven Zen
#: free models: big-pickle aside, every one is `<base>-free`.
_FREE_SUFFIXES = ("-free",)


def _is_free_variant(model: str) -> bool:
    return bool(model) and model.strip().lower().endswith(_FREE_SUFFIXES)


def _rate(nano_per_million: int | None, tokens: int) -> float:
    """Convert a nano-USD-per-1M rate into dollars for ``tokens``.

    ``None`` means the tier does not exist, so the component is skipped
    entirely rather than counted as zero — see the Modelly docs on null vs 0.
    """
    if nano_per_million is None or tokens <= 0:
        return 0.0
    return (tokens / TOKENS_PER_UNIT) * (nano_per_million / NANO_PER_USD)
