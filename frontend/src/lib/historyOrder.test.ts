import { test } from "node:test";
import assert from "node:assert/strict";
import { reconcileHistoryOrder } from "./historyOrder";

test("concurrent recency updates do not move existing chat rows", () => {
  assert.deepEqual(reconcileHistoryOrder(["a", "b", "c"], ["c", "a", "b"]), [
    "a",
    "b",
    "c",
  ]);
});
test("new chats are retained and removed chats do not leave gaps", () => {
  assert.deepEqual(reconcileHistoryOrder(["a", "b", "c"], ["new", "c", "a"]), [
    "a",
    "c",
    "new",
  ]);
  assert.deepEqual(reconcileHistoryOrder([], ["new", "c", "a"]), [
    "new",
    "c",
    "a",
  ]);
});
