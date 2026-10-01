"""Client for the Modelly local price catalog.

Modelly (``Repos/modelly``) runs a read-only HTTP API on ``127.0.0.1:47113``
whenever its desktop app is open. It is the authority for what a model costs;
this module fetches from it, caches the answers to disk, and serves from that
cache when the app is closed.

Three properties of Modelly's API that this client is built around — all three
are called out in its own docs, and all three are easy to get wrong:

**Prices are integers in nano-USD per million tokens.** ``input_nano:
3625000`` is $0.003625 per 1M tokens. They are integers precisely so that
values like $0.003625 and $0.0028 compare exactly; parsing them as floats
reintroduces the rounding noise the integer encoding exists to avoid. We keep
them as ``int`` and divide only when computing a final dollar figure.

**``null`` is not zero.** A ``null`` rate means the tier does not exist; ``0``
means it is genuinely free. Coercing null to zero would silently report paid
models as free, so ``None`` is preserved end to end and a missing rate excludes
that component from the total rather than adding nothing to it.

**Tiers are context-dependent.** A model with long-context pricing has more than
one tier, and the first is only the base rate. The correct tier is chosen by the
request's input size; ignoring the rest understates cost by up to 2x.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_BASE_URL = "http://127.0.0.1:47113/v1"

#: nano-USD per million tokens -> USD per token
NANO_PER_USD = 1_000_000_000
TOKENS_PER_UNIT = 1_000_000


class ModellyUnavailable(RuntimeError):
    """Modelly is not running, or not reachable."""


@dataclass
class Tier:
    """One context-size band of a seller's price list.

    Every ``*_nano`` field is ``None`` when that tier does not exist, which is
    distinct from ``0`` meaning free.
    """

    min_tokens: int = 0
    max_tokens: int | None = None
    input_nano: int | None = None
    output_nano: int | None = None
    cached_read_nano: int | None = None
    cached_write_nano: int | None = None

    def applies_to(self, input_tokens: int) -> bool:
        if input_tokens < self.min_tokens:
            return False
        return self.max_tokens is None or input_tokens < self.max_tokens

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> "Tier":
        return cls(
            min_tokens=int(raw.get("min_tokens") or 0),
            max_tokens=_optional_int(raw.get("max_tokens")),
            input_nano=_optional_int(raw.get("input_nano")),
            output_nano=_optional_int(raw.get("output_nano")),
            cached_read_nano=_optional_int(raw.get("cached_read_nano")),
            cached_write_nano=_optional_int(raw.get("cached_write_nano")),
        )


@dataclass
class Seller:
    """One plan's offering of a model."""

    plan_id: str
    plan_name: str
    offering_id: str = ""
    vendor_model_id: str = ""
    source_id: str = ""
    tiers: list[Tier] = field(default_factory=list)

    #: When this price became true in the world.
    valid_from: str | None = None
    #: When Modelly first observed it. Differs from ``valid_from`` when a vendor
    #: published an effective date; equal to it when the date was inferred.
    observed_at: str | None = None
    #: "stated" if the source published an effective date, "observed" if Modelly
    #: inferred it from first sighting. An "observed" date is a lower bound on
    #: how far back the price can be trusted, not the date it actually changed.
    provenance: str | None = None

    def tier_for(self, input_tokens: int) -> Tier | None:
        for tier in self.tiers:
            if tier.applies_to(input_tokens):
                return tier
        return self.tiers[0] if self.tiers else None

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> "Seller":
        return cls(
            plan_id=str(raw.get("plan_id") or ""),
            plan_name=str(raw.get("plan_name") or raw.get("plan_id") or ""),
            offering_id=str(raw.get("offering_id") or ""),
            vendor_model_id=str(raw.get("vendor_model_id") or ""),
            source_id=str(raw.get("source_id") or ""),
            tiers=[Tier.from_json(t) for t in (raw.get("tiers") or []) if isinstance(t, dict)],
            valid_from=raw.get("valid_from"),
            observed_at=raw.get("observed_at"),
            provenance=raw.get("provenance"),
        )


@dataclass
class ModelPricing:
    """A model as Modelly describes it, with every seller that carries it."""

    model_id: str
    name: str = ""
    creator: str = ""
    family: str = ""
    context_window: int | None = None
    aliases: list[str] = field(default_factory=list)
    sellers: list[Seller] = field(default_factory=list)

    def seller_for(self, plan_hints: list[str]) -> Seller | None:
        """Pick the seller matching the provider a session actually used.

        OpenCode Go and Zen publish different rates for the same model — Go is
        roughly 4x cheaper on DeepSeek V4 Pro and 40x on its cached reads — so
        picking the wrong seller is not a rounding error. Hints are tried in
        order; only if none match do we fall back to the cheapest, which at
        least errs toward under-reporting rather than inventing spend.
        """
        for hint in plan_hints:
            if not hint:
                continue
            for seller in self.sellers:
                if seller.plan_id == hint:
                    return seller
            # Then a looser match, so "opencode-go" finds "opencode-go-sub".
            for seller in self.sellers:
                if hint in seller.plan_id:
                    return seller

        if not self.sellers:
            return None
        return min(self.sellers, key=_cheapest_input)

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> "ModelPricing":
        return cls(
            model_id=str(raw.get("model_id") or ""),
            name=str(raw.get("name") or ""),
            creator=str(raw.get("creator") or ""),
            family=str(raw.get("family") or ""),
            context_window=_optional_int(raw.get("context_window")),
            aliases=[str(a) for a in (raw.get("aliases") or [])],
            sellers=[
                Seller.from_json(s) for s in (raw.get("sellers") or []) if isinstance(s, dict)
            ],
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "name": self.name,
            "creator": self.creator,
            "family": self.family,
            "context_window": self.context_window,
            "aliases": self.aliases,
            "sellers": [
                {
                    "plan_id": s.plan_id,
                    "plan_name": s.plan_name,
                    "offering_id": s.offering_id,
                    "vendor_model_id": s.vendor_model_id,
                    "source_id": s.source_id,
                    "valid_from": s.valid_from,
                    "observed_at": s.observed_at,
                    "provenance": s.provenance,
                    "tiers": [
                        {
                            "min_tokens": t.min_tokens,
                            "max_tokens": t.max_tokens,
                            "input_nano": t.input_nano,
                            "output_nano": t.output_nano,
                            "cached_read_nano": t.cached_read_nano,
                            "cached_write_nano": t.cached_write_nano,
                        }
                        for t in s.tiers
                    ],
                }
                for s in self.sellers
            ],
        }


class ModellyClient:
    """Talks to the Modelly API. Every call is a GET; the API is read-only."""

    def __init__(self, base_url: str = DEFAULT_BASE_URL, timeout: float = 4.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _get(self, path: str) -> Any:
        url = f"{self.base_url}{path}"
        try:
            with urllib.request.urlopen(url, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            raise ModellyUnavailable(f"{url} returned HTTP {exc.code}") from exc
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise ModellyUnavailable(f"{url} unreachable: {exc}") from exc

        # Everything is wrapped in {meta, data}.
        return payload.get("data") if isinstance(payload, dict) else payload

    def health(self) -> dict[str, Any]:
        """Row counts as well as liveness — an empty catalog looks like a
        working API that returns nothing, so check ``priced_offerings``."""
        return self._get("/health") or {}

    def model(self, model_id: str) -> ModelPricing | None:
        """One model, every seller. Resolves through Modelly's alias table, so
        ``claude-opus-4-8``, ``Claude Opus 4.8`` and ``anthropic/claude-opus-4-8``
        all work."""
        raw = self._get(f"/models/{urllib.parse.quote(model_id, safe='')}")
        if not isinstance(raw, dict):
            return None
        return ModelPricing.from_json(raw)

    def prices_as_of(self, model: str, as_of: str) -> list[dict[str, Any]]:
        """What ``model`` cost at ``as_of`` across every seller.

        This is the bitemporal query Modelly exists for: a single indexed range
        check, not a replay of the change log. Returns an empty list when the
        date predates collection — which is a real answer ("we have no record
        of what this cost then"), not an error.
        """
        query = urllib.parse.urlencode({"model": model, "as_of": as_of})
        raw = self._get(f"/prices?{query}")
        return raw if isinstance(raw, list) else []

    def earliest_observation(self) -> str | None:
        """Oldest ``valid_from`` in the catalog — the horizon of what we know.

        Sessions older than this cannot be priced historically, and pricing them
        at today's rates is an assumption that should be labelled as one.
        """
        raw = self._get("/prices?limit=5000")
        if not isinstance(raw, list):
            return None
        dates = [r.get("valid_from") for r in raw if isinstance(r, dict) and r.get("valid_from")]
        return min(dates) if dates else None

    def plans(self) -> list[dict[str, Any]]:
        """Sellers and their subscription terms, for the Stats page."""
        raw = self._get("/plans")
        return raw if isinstance(raw, list) else []


def _optional_int(value: Any) -> int | None:
    """Preserve ``None``. See the module docstring: null is not zero."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _cheapest_input(seller: Seller) -> int:
    rates = [t.input_nano for t in seller.tiers if t.input_nano is not None]
    return min(rates) if rates else 1 << 62
