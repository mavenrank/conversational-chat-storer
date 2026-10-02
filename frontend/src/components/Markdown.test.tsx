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
  const html = renderToStaticMarkup(
    <Markdown text={"## Features\r\n\r\nA paragraph\r\n"} />,
  );
  assert.ok(html.includes("Features"));
  assert.ok(html.includes("A paragraph"));
  assert.ok(!html.includes("## Features"));
});

test("uneven Markdown rows keep the header's column boundaries", () => {
  const html = renderToStaticMarkup(
    <Markdown
      text={
        "| Name | Status | Notes |\n| --- | --- | --- |\n| Short | Ready |\n| Full | Ready | Kept | Extra |"
      }
    />,
  );
  const rows = [...html.matchAll(/<tr>(.*?)<\/tr>/g)].map((match) => match[1]);
  assert.equal(rows.length, 3);
  assert.equal((rows[0].match(/scope="col"/g) ?? []).length, 3);
  assert.equal((rows[1].match(/<td>/g) ?? []).length, 3);
  assert.ok(rows[1].endsWith("<td></td>"));
  assert.equal((rows[2].match(/<td>/g) ?? []).length, 3);
  assert.ok(rows[2].includes("Kept"));
  assert.ok(!rows[2].includes("Extra"));
});
