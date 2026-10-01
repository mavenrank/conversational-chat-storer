# Costs

CCS keeps source-recorded costs separate from API estimates. A recorded zero is
preserved. An unknown model, missing rate, or missing usage stays unavailable;
model names containing “free” are not proof of a zero price.

The active catalog is `backend/ccsweb/pricing/verified_rates.json`, checked on
October 2, 2026 against [OpenAI pricing](https://developers.openai.com/api/docs/pricing)
and the GPT-5.6 and GPT-6 model pages,
[Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing), and
[Google pricing](https://ai.google.dev/gemini-api/docs/pricing). It covers verified
models found in local Codex, Claude, and Gemini history. Models without a verified
entry, including internal review models, are listed in Settings.

Estimates describe the equivalent token cost at **current standard text API rates**.
They are not historical invoices or subscription charges. Premium service tiers,
regional modifiers, promotional gateway prices, tool charges, multimedia rates,
and cache storage fees are excluded. No provider credentials are used and no chat
content is sent to pricing sites.

Pricing runs in the background and caches results by file signature. History can
load while estimates are calculated. Settings shows progress, coverage, the rate
date, and source links. Recheck refreshes local usage; rate changes require a
reviewed catalog update, rather than scraping providers during normal browsing.

Codex is priced from request-level token records, not cumulative session context.
Modern response IDs are deduplicated and supersede legacy token counters for the
same turn. Model changes and long-context thresholds are applied per request.
Repeated Claude response usage is counted once; cache reads, short cache writes,
and one-hour cache writes are accounted for separately.

Totals include agent runs. Alternate duplicate transcripts hidden by an adapter
are excluded. When some requests cannot be priced, the estimate is explicitly
partial. The older Modelly cache and YAML utilities are retained separately and
are not used by the active cost endpoint.
