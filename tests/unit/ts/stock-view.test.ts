import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { clampDelta, serialize, settleStep } from "../../../frontend/src/screens/stock/stepper.ts";
import { bulkDeleteNeedsConfirm, filterItems, groupingFromParam, matchesQuery } from "../../../frontend/src/screens/stock/stock-view.ts";

describe("settleStep", () => {
  test("negative delta is a sale, positive a delivery", () => {
    assert.deepEqual(settleStep(10, -3), { next: 7, notes: "Sold 3" });
    assert.deepEqual(settleStep(10, 2), { next: 12, notes: "Received 2" });
  });
  test("never goes below zero and notes the real change", () => {
    assert.deepEqual(settleStep(2, -5), { next: 0, notes: "Sold 2" });
  });
  test("no change gives null", () => {
    assert.equal(settleStep(4, 0), null);
    assert.equal(settleStep(0, -1), null);
  });
});

describe("clampDelta", () => {
  test("stops at zero", () => {
    assert.equal(clampDelta(0, -1), 0);
    assert.equal(clampDelta(1, -1), -1);
    assert.equal(clampDelta(3, -5), -3);
    assert.equal(clampDelta(0, 1), 1);
  });
});

describe("groupingFromParam", () => {
  test("defaults to category; status only when asked", () => {
    assert.equal(groupingFromParam(null), "category");
    assert.equal(groupingFromParam("category"), "category");
    assert.equal(groupingFromParam("junk"), "category");
    assert.equal(groupingFromParam("status"), "status");
  });
});

describe("filterItems", () => {
  test('"order" keeps out and low items', () => {
    const items = [
      { name: "a", quantity: 0 },
      { name: "b", quantity: 3, lowStockThreshold: 5 },
      { name: "c", quantity: 50 },
    ];
    assert.deepEqual(
      filterItems(items, "order", "").map((item) => item.name),
      ["a", "b"],
    );
  });
});

describe("matchesQuery", () => {
  test("matches the size in description", () => {
    assert.equal(matchesQuery({ name: "Coke", description: "1.5L" }, "1.5l"), true);
    assert.equal(matchesQuery({ name: "Coke", description: "1.5L" }, "330ml"), false);
  });
});

describe("serialize", () => {
  test("a write queued behind another gets its result, not a stale store read", async () => {
    const queue = new Map<string, Promise<number>>();
    let release = (_value: number) => {};
    const first = new Promise<number>((resolve) => (release = resolve));
    const seen: (number | undefined)[] = [];
    void serialize(queue, "a", (previous) => {
      seen.push(previous);
      return first;
    });
    const second = serialize(queue, "a", async (previous) => {
      seen.push(previous);
      return 3;
    });
    release(2);
    assert.equal(await second, 3);
    assert.deepEqual(seen, [undefined, 2]);
  });
  test("the queue forgets a key once its last write settles", async () => {
    const queue = new Map<string, Promise<number>>();
    await serialize(queue, "a", async () => 1);
    await Promise.resolve();
    assert.equal(queue.has("a"), false);
  });
});

describe("bulkDeleteNeedsConfirm", () => {
  test("fewer than 10 selected rows delete without a confirm", () => {
    assert.equal(bulkDeleteNeedsConfirm(9, 50), false);
    assert.equal(bulkDeleteNeedsConfirm(1, 50), false);
  });
  test("10 or more always confirm", () => {
    assert.equal(bulkDeleteNeedsConfirm(10, 50), true);
  });
  test("every shown row selected (Select all) confirms", () => {
    assert.equal(bulkDeleteNeedsConfirm(3, 3), true);
  });
});
