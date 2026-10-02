"""Populate the pricing cache from Modelly.

Run this on the machine where Modelly's desktop app is open:

    uv run python -m ccsweb.pricing.sync

It walks every session, collects the distinct (provider, model) pairs actually
used, asks Modelly about each, and writes the answers to
``ccsweb/pricing/model_cache.json``. After that, pricing works with Modelly
closed and with no network at all.

Anything Modelly does not know is printed at the end under "additional details
necessary" — those are the models to add to Modelly, not to guess at here.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ccsweb.pricing.catalog import PricingCatalog
from ccsweb.pricing.modelly import DEFAULT_BASE_URL, ModellyClient, ModellyUnavailable
from ccsweb.registry import Registry

CACHE_PATH = Path(__file__).with_name("model_cache.json")


#: Values that appear where a model id is expected but are not models. Sending
#: these to Modelly produces confusing "no pricing for xAI" output; they are
#: vendors, placeholders, or artefacts.
_NOT_MODELS = {
    "<synthetic>",
    "synthetic",
    "unknown",
    "none",
    "null",
    "",
    # Vendor names, in case an adapter still leaks one through.
    "minimax",
    "xai",
    "anthropic",
    "openai",
    "google",
    "deepseek",
}


def collect_pairs(registry: Registry) -> set[tuple[str, str]]:
    """Every (provider, model) that appears in any session, subagents included.

    Reads the summary directly — no transcript loads. Every adapter now reports
    both ``models`` and ``providers`` on the summary, which is what makes this
    fast enough to run over a few hundred sessions.
    """
    pairs: set[tuple[str, str]] = set()
    for summary in registry.list_sessions(
        include_subagents=True, include_forks=True, include_approval_reviews=True
    ):
        providers = summary.providers or [""]
        for model in summary.models:
            if model.strip().lower() in _NOT_MODELS:
                continue
            for provider in providers:
                pairs.add((provider, model))
    return pairs


def sessions_without_models(registry: Registry) -> dict[str, int]:
    """Sources whose sessions record no model id at all.

    Kilocode is the known case: it stores ``inferenceProvider`` but never the
    model, in any of its three files. Those sessions cannot be priced from a
    catalog and must fall back to the ``cost`` the tool recorded itself.
    """
    counts: dict[str, int] = {}
    for summary in registry.list_sessions(
        include_subagents=True, include_forks=True, include_approval_reviews=True
    ):
        usable = [m for m in summary.models if m.strip().lower() not in _NOT_MODELS]
        if not usable:
            counts[summary.source] = counts.get(summary.source, 0) + 1
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--cache", type=Path, default=CACHE_PATH)
    parser.add_argument(
        "--models",
        nargs="*",
        help="Sync only these model ids instead of scanning sessions.",
    )
    args = parser.parse_args()

    client = ModellyClient(args.base_url)
    try:
        health = client.health()
    except ModellyUnavailable as exc:
        print(f"Modelly is not reachable at {args.base_url}")
        print(f"  {exc}")
        print("\nOpen the Modelly desktop app, then run this again.")
        return 1

    print(
        f"Modelly: {health.get('models', 0)} models, "
        f"{health.get('priced_offerings', 0)} priced offerings, "
        f"last refresh {health.get('last_refresh_at', 'unknown')}"
    )
    if not health.get("priced_offerings"):
        print("\nThe catalog is empty. Run a refresh in Modelly's Sources tab first.")
        return 1

    catalog = PricingCatalog(args.cache, client=client, allow_network=True)

    unmodelled: dict[str, int] = {}
    if args.models:
        wanted = {(None, m) for m in args.models}
    else:
        print("\nScanning sessions for models in use…")
        registry = Registry.from_settings()
        wanted = {(p or None, m) for p, m in collect_pairs(registry)}
        unmodelled = sessions_without_models(registry)

    models = sorted({m for _, m in wanted})
    providers = sorted({p for p, _ in wanted if p})
    print(
        f"{len(models)} distinct model(s) across "
        f"{len(providers)} provider(s): {', '.join(providers) or 'none recorded'}\n"
    )

    resolved, missing = [], []
    for model in models:
        pricing, basis = catalog.lookup(model)
        if pricing is None:
            missing.append(model)
            print(f"  MISS  {model}")
        else:
            resolved.append(model)
            sellers = ", ".join(sorted({s.plan_id for s in pricing.sellers})) or "none"
            print(f"  ok    {model:28} -> {pricing.model_id}  [{sellers}]")

    catalog.save()
    print(f"\nCached {catalog.cached_model_count} entries to {args.cache}")

    if missing:
        print("\nadditional details necessary — Modelly has no pricing for:")
        for model in missing:
            print(f"  - {model}")
        print("\nAdd these to Modelly (or a source it scrapes); they are excluded")
        print("from cost totals rather than being priced at zero.")

    if unmodelled:
        print("\nSources whose sessions record no model id (cannot be catalog-priced):")
        for source, count in sorted(unmodelled.items()):
            print(f"  - {source}: {count} session(s)")
        print("\nThese fall back to the cost the tool recorded itself, where it")
        print("has one. Kilocode does record a per-request `cost`, so its totals")
        print("are still real; they just do not come from Modelly.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
