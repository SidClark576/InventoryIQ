import assert from "node:assert/strict";
import { describe, test } from "node:test";
import type { Transaction } from "../../../frontend/src/lib/activity.ts";
import { buildStockReport, defaultStartDate, isRestock } from "../../../frontend/src/lib/stock-report.ts";

const start = new Date("2026-10-01T00:00:00Z");

describe("stock report", () => {
  test("defaultStartDate is the 1st of the current local month", () => {
    assert.equal(defaultStartDate(new Date(2026, 9, 28, 15)), "2026-10-01");
    assert.equal(defaultStartDate(new Date(2026, 0, 1)), "2026-01-01");
  });

  test("isRestock: Received stock_in and create count, Count fix does not", () => {
    assert.equal(isRestock({ changeType: "stock_in", notes: "Received 12" }), true);
    assert.equal(isRestock({ changeType: "stock_in", notes: "  received: 3" }), true);
    assert.equal(isRestock({ changeType: "create" }), true);
    assert.equal(isRestock({ changeType: "stock_in", notes: "Count fix" }), false);
    assert.equal(isRestock({ changeType: "stock_out", notes: "Received 2" }), false);
  });

  test("starting, stock in and stock now come from transactions since the start", () => {
    const items = [
      { itemID: "a", name: "Sardines", category: "Can goods", description: "155g", price: "53", quantity: 20 },
      { itemID: "b", name: "Corned beef", category: "Can goods", quantity: 5, price: 40 },
      { itemID: "c", name: "Soap", category: "Personal care", quantity: 7, price: 25 },
    ];
    const txs: Transaction[] = [
      { itemID: "a", changeType: "stock_in", quantityDelta: 12, notes: "Received 12", createdAt: "2026-10-05T03:00:00+00:00" },
      { itemID: "a", changeType: "stock_out", quantityDelta: -4, notes: "Sold 4", createdAt: "2026-10-06T03:00:00+00:00" },
      { itemID: "a", changeType: "stock_in", quantityDelta: 2, notes: "Count fix", createdAt: "2026-10-07T03:00:00+00:00" },
      { itemID: "a", changeType: "stock_in", quantityDelta: 50, notes: "Received 50", createdAt: "2026-09-20T03:00:00+00:00" },
      { itemID: "c", changeType: "create", quantityBefore: 0, quantityAfter: 9, createdAt: "2026-10-10T03:00:00+00:00" },
      { itemID: "c", changeType: "stock_out", quantityDelta: -2, notes: "Sold 2", createdAt: "2026-10-11T03:00:00+00:00" },
    ];
    const [cans, care] = buildStockReport(items, txs, start);
    assert.deepEqual(cans?.rows, [
      { name: "Corned beef", size: "", price: 40, starting: 5, stockIn: 0, now: 5 },
      { name: "Sardines", size: "155g", price: 53, starting: 10, stockIn: 12, now: 20 },
    ]);
    assert.deepEqual(care?.rows, [{ name: "Soap", size: "", price: 25, starting: 0, stockIn: 9, now: 7 }]);
  });

  test("groups sort by category with Uncategorized last, rows by name", () => {
    const items = [
      { itemID: "1", name: "Zest", category: "" },
      { itemID: "2", name: "Bread", category: "Bakery" },
      { itemID: "3", name: "Apple", category: "Produce" },
      { itemID: "4", name: "Bagel", category: "Bakery" },
      { itemID: "5", name: "Apron" },
    ];
    const groups = buildStockReport(items, [], start);
    assert.deepEqual(
      groups.map((group) => [group.category, group.rows.map((row) => row.name)]),
      [
        ["Bakery", ["Bagel", "Bread"]],
        ["Produce", ["Apple"]],
        ["Uncategorized", ["Apron", "Zest"]],
      ],
    );
  });
});
