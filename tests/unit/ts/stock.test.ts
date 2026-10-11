import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  countByLevel,
  priceOf,
  restockQueue,
  thresholdOf,
} from "../../../frontend/src/lib/dashboardStats.ts";
import { nextQuantity, reasonAllows, reasonNote } from "../../../frontend/src/lib/reasons.ts";
import { parseCsv, toCsv } from "../../../frontend/src/lib/csv.ts";

const asNumber = (value: string): number => value as unknown as number;

describe("thresholdOf / priceOf", () => {
  test("coerces strings and falls back to defaults", () => {
    assert.equal(thresholdOf({}), 10);
    assert.equal(thresholdOf({ lowStockThreshold: asNumber("4") }), 4);
    assert.equal(priceOf({ price: asNumber("2.50") }), 2.5);
    assert.equal(priceOf({ price: asNumber("n/a") }), 0);
  });
});

describe("countByLevel", () => {
  test("counts out, low and ok items", () => {
    const counts = countByLevel([
      { quantity: 0 },
      { quantity: 3, lowStockThreshold: 5 },
      { quantity: 50 },
      { quantity: 9 },
    ]);
    assert.deepEqual(counts, { out: 1, low: 2, ok: 1 });
  });
});

describe("restockQueue", () => {
  test("puts out items first, then the furthest below their alert level", () => {
    const queue = restockQueue([
      { name: "Plenty", quantity: 100 },
      { name: "Half", quantity: 5, lowStockThreshold: 10 },
      { name: "Gone", quantity: 0, lowStockThreshold: 3 },
      { name: "Barely", quantity: 1, lowStockThreshold: 10 },
    ]);
    assert.deepEqual(queue.map((item) => item.name), ["Gone", "Barely", "Half"]);
  });

  test("does not mutate its input", () => {
    const items = Object.freeze([Object.freeze({ name: "B", quantity: 1 }), Object.freeze({ name: "A", quantity: 0 })]);
    assert.doesNotThrow(() => restockQueue(items));
  });
});

describe("reasons", () => {
  test("restricts reasons to the direction they describe", () => {
    assert.equal(reasonAllows("Received", "add"), true);
    assert.equal(reasonAllows("Received", "remove"), false);
    assert.equal(reasonAllows("Waste", "add"), false);
    assert.equal(reasonAllows("Count fix", "add"), true);
    assert.equal(reasonAllows(null, "remove"), true);
  });

  test("formats notes the activity filters understand", () => {
    assert.equal(reasonNote("Waste", "remove", 2), "Waste: 2");
    assert.equal(reasonNote("Damaged", "remove", 1), "Damaged: 1");
    assert.equal(reasonNote("Received", "add", 12), "Received 12");
    assert.equal(reasonNote("Count fix", "add", 3), "Count fix");
    assert.equal(reasonNote(null, "remove", 4), "Used 4");
    assert.equal(reasonNote(null, "add", 4), "Received 4");
  });

  test("never goes below zero", () => {
    assert.equal(nextQuantity(3, "remove", 5), 0);
    assert.equal(nextQuantity(3, "add", 5), 8);
  });
});

describe("csv", () => {
  test("round-trips quotes, commas and empty cells", () => {
    const text = toCsv(["name", "notes"], [["Milk, oat", 'say "hi"'], ["Tea", null]]);
    assert.deepEqual(parseCsv(text), [
      { name: "Milk, oat", notes: 'say "hi"' },
      { name: "Tea", notes: "" },
    ]);
  });

  test("skips blank lines and handles CRLF", () => {
    assert.deepEqual(parseCsv("name,quantity\r\nCups,4\r\n\r\n"), [{ name: "Cups", quantity: "4" }]);
    assert.deepEqual(parseCsv(""), []);
  });
});
