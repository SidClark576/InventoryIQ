import type { InventoryItem } from "@/api";

export type StockLevel = "out" | "low" | "ok";

export type StockAlert = {
  itemID?: string;
  name?: string;
  quantity: number;
};

export type DashStats = {
  totalProducts: number;
  outOfStockCount: number;
  lowStockCount: number;
  estimatedInventoryValue: number;
  outOfStockItems: StockAlert[];
  lowStockItems: StockAlert[];
};

// Same default LowItemInsight.py applies when an item has no lowStockThreshold.
const DEFAULT_LOW_STOCK_THRESHOLD = 10;

// CSV-imported rows can carry price and quantity as strings.
function numberOr(value: unknown, fallback: number): number {
  if (value === null || value === undefined || value === "") return fallback;
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

export function quantityOf(item: InventoryItem): number {
  return numberOr(item.quantity, 0);
}

export function thresholdOf(item: InventoryItem): number {
  return numberOr(item.lowStockThreshold, DEFAULT_LOW_STOCK_THRESHOLD);
}

export function priceOf(item: InventoryItem): number {
  return numberOr(item.price, 0);
}

export function stockLevelOf(item: InventoryItem): StockLevel {
  const quantity = quantityOf(item);
  if (quantity <= 0) return "out";
  return quantity <= thresholdOf(item) ? "low" : "ok";
}

export function countByLevel(items: readonly InventoryItem[]): Record<StockLevel, number> {
  return items.reduce<Record<StockLevel, number>>(
    (counts, item) => {
      const level = stockLevelOf(item);
      return { ...counts, [level]: counts[level] + 1 };
    },
    { out: 0, low: 0, ok: 0 },
  );
}

// Quantity as a share of the alert level; lower is more urgent.
function coverOf(item: InventoryItem): number {
  return quantityOf(item) / Math.max(thresholdOf(item), 1);
}

/** Out and low items, most urgent first: out, then furthest below the alert level, then by name. */
export function restockQueue(items: readonly InventoryItem[]): InventoryItem[] {
  return items
    .filter((item) => stockLevelOf(item) !== "ok")
    .sort(
      (a, b) =>
        coverOf(a) - coverOf(b) || String(a.name ?? "").localeCompare(String(b.name ?? "")),
    );
}

function toAlert(item: InventoryItem): StockAlert {
  return { itemID: item.itemID, name: item.name, quantity: quantityOf(item) };
}

export function deriveDashStats(items: readonly InventoryItem[]): DashStats {
  const outOfStockItems = items.filter((item) => stockLevelOf(item) === "out").map(toAlert);
  const lowStockItems = items.filter((item) => stockLevelOf(item) === "low").map(toAlert);
  const estimatedInventoryValue = items.reduce(
    (sum, item) => sum + priceOf(item) * quantityOf(item),
    0,
  );
  return {
    totalProducts: items.length,
    outOfStockCount: outOfStockItems.length,
    lowStockCount: lowStockItems.length,
    estimatedInventoryValue,
    outOfStockItems,
    lowStockItems,
  };
}
