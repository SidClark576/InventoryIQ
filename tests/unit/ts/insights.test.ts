import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { deriveInsights } from "../../../frontend/src/lib/insights.ts";

// 23:30 local on Oct 31: calendar days, not 24h blocks, decide "across 3 days".
const NOW = new Date(2026, 9, 31, 23, 30);
const at = (day: number, hour = 12, minute = 0) => new Date(2026, 9, day, hour, minute).toISOString();
const OLD = new Date(2026, 6, 1).toISOString();

const out = (itemID: string, delta: number, day: number, notes = "Used 1", hour = 12) => ({
  itemID, changeType: "stock_out", quantityDelta: delta, notes, createdAt: at(day, hour),
});
const into = (itemID: string, delta: number, day: number, notes = "Received 1") => ({
  itemID, changeType: "stock_in", quantityDelta: delta, notes, createdAt: at(day),
});

describe("deriveInsights: running out", () => {
  test("estimates from 2+ uses across 3+ calendar days, soonest first, 14 days max", () => {
    const items = [
      { itemID: "a", name: "A", quantity: 10, createdAt: OLD },
      { itemID: "b", name: "B", quantity: 2, createdAt: OLD },
      { itemID: "z", name: "Z", quantity: 0, createdAt: OLD },
      { itemID: "far", name: "Far", quantity: 300, createdAt: OLD },
    ];
    const txs = [
      out("a", -3, 29, "Used 3", 0), out("a", -3, 31, "Sold 3", 23), // 6 over Oct 29..31 = 2/day → 5 days
      out("b", -3, 29), out("b", -3, 30), // 2/day → 1 day
      out("z", -3, 29), out("z", -3, 30),
      out("far", -3, 29), out("far", -3, 30),
    ];
    const { runningOut, estimated } = deriveInsights(items, txs, NOW);
    assert.deepEqual(runningOut.map((r) => [r.item.itemID, r.daysLeft]), [["b", 1], ["a", 5]]);
    assert.equal(estimated, 3); // a, b, far (z is out of stock)
  });

  test("two uses within two calendar days are not enough", () => {
    const items = [{ itemID: "a", quantity: 5, createdAt: OLD }];
    const txs = [out("a", -2, 30, "Used 2", 1), out("a", -2, 31, "Used 2", 23)];
    assert.equal(deriveInsights(items, txs, NOW).estimated, 0);
  });

  test("waste, damage and count fixes are not use; Undo of a sale nets it out", () => {
    const items = [{ itemID: "a", quantity: 6, createdAt: OLD }, { itemID: "w", quantity: 6, createdAt: OLD }];
    const txs = [
      out("a", -5, 29, "Used 5"), out("a", -5, 30, "Used 5"), into("a", 5, 30, "Undo"), // net 5 over 3 days
      out("w", -5, 29, "Waste: 5"), out("w", -5, 30, "Damaged: 5"), out("w", -1, 30, "Count fix"), out("w", -1, 29, "Used 1"),
    ];
    const { runningOut, estimated } = deriveInsights(items, txs, NOW);
    assert.deepEqual(runningOut.map((r) => [r.item.itemID, r.daysLeft]), [["a", 4]]); // 6 / (5/3) = 3.6 → 4
    assert.equal(estimated, 1);
  });
});

describe("deriveInsights: expiring, not moving, waste, health, categories", () => {
  test("expiring within 7 days, expired first, in-stock only", () => {
    const items = [
      { itemID: "soon", quantity: 1, expiresAt: "2026-11-03" },
      { itemID: "gone", quantity: 1, expiresAt: "2026-10-30" },
      { itemID: "later", quantity: 1, expiresAt: "2026-11-08" },
      { itemID: "empty", quantity: 0, expiresAt: "2026-11-01" },
      { itemID: "undated", quantity: 1 },
    ];
    assert.deepEqual(deriveInsights(items, [], NOW).expiring.map((e) => [e.item.itemID, e.days]), [["gone", -1], ["soon", 3]]);
  });

  test("not moving: in stock, 30+ days old, no stock in/out for 30 days", () => {
    const items = [
      { itemID: "still", quantity: 4, createdAt: OLD },
      { itemID: "young", quantity: 4, createdAt: at(20) },
      { itemID: "sold", quantity: 4, createdAt: OLD },
      { itemID: "none", quantity: 0, createdAt: OLD },
      { itemID: "legacy", quantity: 4 },
    ];
    const txs = [out("sold", -1, 15), { itemID: "still", changeType: "update", notes: "", createdAt: at(15) }];
    assert.deepEqual(deriveInsights(items, txs, NOW).notMoving.map((i) => i.itemID), ["still", "legacy"]);
  });

  test("waste and damage totals in units and value", () => {
    const items = [{ itemID: "a", quantity: 1, price: "2.5" }];
    const txs = [out("a", -2, 30, "Waste: 2"), out("a", -1, 30, "Damaged: 1"), out("a", -4, 30, "Used 4"), out("a", -9, 1, "Waste: 9")];
    assert.deepEqual(deriveInsights(items, txs, NOW).waste, { units: 3, value: 7.5, changes: 2 });
  });

  test("health is the share of healthy stock: out counts 1, low 0.4, none for an empty store", () => {
    assert.equal(deriveInsights([], [], NOW).health, null);
    const items = [{ quantity: 0 }, { quantity: 2, lowStockThreshold: 5 }, { quantity: 3 }, { quantity: 50 }];
    assert.equal(deriveInsights(items, [], NOW).health, 55);
    assert.equal(deriveInsights(Array.from({ length: 5 }, () => ({ quantity: 0 })), [], NOW).health, 0);
    const bigStore = [...Array.from({ length: 4 }, () => ({ quantity: 0 })), ...Array.from({ length: 6 }, () => ({ quantity: 50 }))];
    assert.equal(deriveInsights(bigStore, [], NOW).health, 60);
  });

  test("category risk, riskiest first", () => {
    const items = [
      { category: "Drinks", quantity: 0 }, { category: "Drinks", quantity: 50 },
      { category: "Snacks", quantity: 50 }, { quantity: 1 },
    ];
    assert.deepEqual(deriveInsights(items, [], NOW).categoryRisk, [
      { category: "Uncategorized", atRisk: 1, total: 1, percent: 100 },
      { category: "Drinks", atRisk: 1, total: 2, percent: 50 },
      { category: "Snacks", atRisk: 0, total: 1, percent: 0 },
    ]);
  });
});
