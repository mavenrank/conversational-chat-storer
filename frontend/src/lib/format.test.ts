import { describe, test } from "node:test";
import assert from "node:assert/strict";
import { formatRelative, parseTimestamp } from "./format";

describe("chat timestamps", () => {
  test("legacy UTC, explicit UTC and offsets describe the same instant", () => {
    const instant = Date.UTC(2026, 9, 1, 11, 30);
    for (const value of ["2026-10-01T11:30:00", "2026-10-01T11:30:00Z", "2026-10-01T17:00:00+05:30"]) {
      assert.equal(parseTimestamp(value).getTime(), instant);
    }
  });
  test("invalid and future dates do not masquerade as active chats", () => {
    assert.equal(formatRelative("invalid"), "");
    assert.notEqual(formatRelative(new Date(Date.now() + 86_400_000).toISOString()), "just now");
  });
});
