import assert from "node:assert/strict";
import { describe, test } from "node:test";
import type { InventoryItem } from "../../../frontend/src/api.ts";
import {
  daysUntilExpiry,
  deriveDashStats,
  expiryLevelOf,
  quantityOf,
  stockLevelOf,
} from "../../../frontend/src/lib/dashboardStats.ts";

// CSV-imported rows arrive with numeric fields as strings.
const asNumber = (value: string): number => value as unknown as number;

describe("stockLevelOf", () => {
  test("classifies qty<=0 as out, qty<=threshold as low, otherwise ok", () => {
    assert.equal(stockLevelOf({ quantity: 0, lowStockThreshold: 5 }), "out");
    assert.equal(stockLevelOf({ quantity: -2, lowStockThreshold: 5 }), "out");
    assert.equal(stockLevelOf({ quantity: 1, lowStockThreshold: 5 }), "low");
    assert.equal(stockLevelOf({ quantity: 5, lowStockThreshold: 5 }), "low");
    assert.equal(stockLevelOf({ quantity: 6, lowStockThreshold: 5 }), "ok");
  });

  test("defaults a missing threshold to 10 and a missing quantity to 0", () => {
    assert.equal(stockLevelOf({ quantity: 10 }), "low");
    assert.equal(stockLevelOf({ quantity: 11 }), "ok");
    assert.equal(stockLevelOf({}), "out");
    assert.equal(quantityOf({ quantity: undefined }), 0);
  });
});

describe("deriveDashStats", () => {
  test("returns zeroed stats for an empty list", () => {
    const stats = deriveDashStats([]);

    assert.deepEqual(
      [stats.totalProducts, stats.outOfStockCount, stats.lowStockCount, stats.estimatedInventoryValue],
      [0, 0, 0, 0],
    );
    assert.deepEqual(stats.outOfStockItems, []);
    assert.deepEqual(stats.lowStockItems, []);
  });

  test("coerces string prices and quantities from CSV import", () => {
    const stats = deriveDashStats([
      { itemID: "a", name: "A", quantity: asNumber("3"), price: asNumber("10.00"), lowStockThreshold: 5 },
      { itemID: "b", name: "B", quantity: 4, price: asNumber("0.5") },
    ]);

    assert.equal(stats.estimatedInventoryValue, 32);
    assert.equal(stats.lowStockCount, 2);
  });

  test("treats an unparseable price as 0 instead of producing NaN", () => {
    const stats = deriveDashStats([
      { quantity: 5, price: asNumber("n/a") },
      { quantity: 2, price: 3 },
    ]);

    assert.equal(stats.estimatedInventoryValue, 6);
  });

  test("matches the LowItemInsight.py classification on a mixed list", () => {
    const stats = deriveDashStats([
      { itemID: "1", name: "Widget", quantity: 0, price: 2.5, lowStockThreshold: 5 },
      { itemID: "2", name: "Gadget", quantity: 3, price: 10, lowStockThreshold: 5 },
      { itemID: "3", name: "Gizmo", quantity: 40, price: 1.25 },
      { itemID: "4", name: "Doohickey", quantity: 10, price: 0.5 },
    ]);

    assert.equal(stats.totalProducts, 4);
    assert.equal(stats.outOfStockCount, 1);
    assert.equal(stats.lowStockCount, 2);
    assert.equal(stats.estimatedInventoryValue, 85);
    assert.deepEqual(stats.outOfStockItems, [{ itemID: "1", name: "Widget", quantity: 0 }]);
    assert.deepEqual(
      stats.lowStockItems.map((alert) => alert.name),
      ["Gadget", "Doohickey"],
    );
  });

  test("does not mutate its input", () => {
    const items: readonly InventoryItem[] = Object.freeze([
      Object.freeze({ itemID: "1", quantity: 0 }),
    ]);

    assert.doesNotThrow(() => deriveDashStats(items));
  });
});

describe("expiryLevelOf", () => {
  // Local calendar day, as the browser sees it.
  const today = new Date(2026, 10, 10, 23, 30);

  test("past is expired, today through +7 days is soon, later or missing is null", () => {
    assert.equal(expiryLevelOf({ expiresAt: "2026-11-09" }, today), "expired");
    assert.equal(expiryLevelOf({ expiresAt: "2026-11-10" }, today), "soon");
    assert.equal(expiryLevelOf({ expiresAt: "2026-11-17" }, today), "soon");
    assert.equal(expiryLevelOf({ expiresAt: "2026-11-18" }, today), null);
    assert.equal(expiryLevelOf({ expiresAt: "" }, today), null);
    assert.equal(expiryLevelOf({}, today), null);
  });

  test("daysUntilExpiry counts calendar days", () => {
    assert.equal(daysUntilExpiry({ expiresAt: "2026-11-13" }, today), 3);
    assert.equal(daysUntilExpiry({ expiresAt: "2026-11-09" }, today), -1);
    assert.equal(daysUntilExpiry({ expiresAt: "2027-01-01" }, today), 52);
    assert.equal(daysUntilExpiry({}, today), null);
  });
});
