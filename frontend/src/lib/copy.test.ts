import { test } from "node:test";
import assert from "node:assert/strict";
import { copyOptions, resolveCopyText } from "./copy";
import type { Block } from "./types";

const prose: Block = { kind: "text", text: "The reply." };
const thinking: Block = {
  kind: "thinking",
  text: "",
  subject: null,
  elided: true,
  size_bytes: 5000,
};
const tool = {
  kind: "tool_use",
  tool_id: "call",
  name: "codex_app.list_artifacts",
  status: "completed",
  error: null,
  duration_ms: null,
  detail: {
    category: "generic",
    input: { kind: "pull_request" },
    output: "",
    elided: true,
    size_bytes: 5000,
  },
} satisfies Block;

test("plain messages have one copy action; additional scopes include distinct content", () => {
  assert.deepEqual(copyOptions([prose], true), [
    { scope: "answer", label: "Copy message" },
  ]);
  assert.deepEqual(
    copyOptions([tool, prose]).map((option) => option.scope),
    ["answer", "tools"],
  );
  assert.deepEqual(
    copyOptions([thinking, tool, prose]).map((option) => option.scope),
    ["answer", "tools", "full"],
  );
  assert.deepEqual(copyOptions([thinking]), [
    { scope: "full", label: "Copy reasoning" },
  ]);
  assert.deepEqual(copyOptions([]), []);
});

test("copy resolves collapsed content with original references and only the selected scope", async () => {
  const refs: number[] = [];
  const load = async (index: number): Promise<Block> => {
    refs.push(index);
    return index === 0
      ? { ...thinking, text: "Reasoning content", elided: false }
      : {
          ...tool,
          detail: { ...tool.detail, output: "Complete result", elided: false },
        };
  };
  const blocks = [thinking, prose, tool];
  assert.equal(await resolveCopyText(blocks, "answer", load), "The reply.");
  assert.deepEqual(refs, []);
  const withTools = await resolveCopyText(blocks, "tools", load);
  assert.deepEqual(refs, [2]);
  assert.ok(withTools.includes("Complete result"));
  assert.ok(withTools.includes('"kind": "pull_request"'));
  assert.ok(!withTools.includes("Reasoning content"));
  refs.length = 0;
  const full = await resolveCopyText(blocks, "full", load);
  assert.deepEqual(refs, [0, 2]);
  assert.ok(full.includes("Reasoning content"));
  assert.ok(!full.includes("collapsed"));
  assert.equal(thinking.text, "");
  await assert.rejects(
    resolveCopyText(blocks, "full", async () => {
      throw new Error("Load failed");
    }),
    /Load failed/,
  );
});
