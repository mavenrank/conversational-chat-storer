import { test } from "node:test";
import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";
import { Markdown } from "./Markdown";

test("malformed headings with Unicode line separators remain readable", () => {
  const text = "# First\u2028second\n\n## Third\u2029fourth\n\nLast line";
  const html = renderToStaticMarkup(<Markdown text={text} />);
  assert.ok(html.includes("First"));
  assert.ok(html.includes("fourth"));
  assert.ok(html.includes("Last line"));
});

test("Windows line endings render headings without stalling", () => {
  const html = renderToStaticMarkup(<Markdown text={"## Features\r\n\r\nA paragraph\r\n"} />);
  assert.ok(html.includes("Features"));
  assert.ok(html.includes("A paragraph"));
  assert.ok(!html.includes("## Features"));
});
