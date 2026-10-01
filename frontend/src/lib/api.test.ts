import { test } from "node:test";
import assert from "node:assert/strict";
import { api } from "./api";

test("all session pages load with source and agent filters preserved", async () => {
  const originalFetch = globalThis.fetch;
  const offsets: number[] = [];
  globalThis.fetch = (async (input: RequestInfo | URL) => {
    const url = new URL(String(input), "http://localhost");
    assert.deepEqual(url.searchParams.getAll("source"), ["codex"]);
    assert.equal(url.searchParams.get("include_subagents"), "true");
    const offset = Number(url.searchParams.get("offset"));
    const limit = Number(url.searchParams.get("limit"));
    offsets.push(offset);
    const sessions = Array.from({ length: Math.min(limit, 2025 - offset) }, (_, i) => ({ id: `codex:${offset + i}` }));
    return new Response(JSON.stringify(sessions));
  }) as typeof fetch;
  try {
    const sessions = await api.sessions({ sources: ["codex"], includeSubagents: true });
    assert.equal(sessions.length, 2025);
    assert.deepEqual(offsets, [0, 1000, 2000]);
    assert.equal(sessions.at(-1)?.id, "codex:2024");
  } finally {
    globalThis.fetch = originalFetch;
  }
});
