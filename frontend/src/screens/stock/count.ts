import type { InventoryItem } from "@/api";
// Relative .ts import so node:test can load this module (no `@/` resolution there).
import { quantityOf } from "../../lib/dashboardStats.ts";

/** Typed counts keyed by itemID; a blank entry means "not counted". */
export type Counts = Readonly<Record<string, string>>;

export type CountChange = {
  item: InventoryItem;
  expected: number;
  counted: number;
};

export function countedValue(raw: string | undefined): number | null {
  if (raw === undefined || raw.trim() === "") return null;
  const value = Number(raw);
  return Number.isInteger(value) && value >= 0 ? value : null;
}

export function summarizeCount(items: readonly InventoryItem[], counts: Counts) {
  const counted = items.filter((item) => item.itemID && countedValue(counts[item.itemID]) !== null);
  const changes: CountChange[] = counted
    .map((item) => ({
      item,
      expected: quantityOf(item),
      counted: countedValue(counts[item.itemID ?? ""]) ?? 0,
    }))
    .filter((change) => change.counted !== change.expected)
    .sort((a, b) => Math.abs(b.counted - b.expected) - Math.abs(a.counted - a.expected));
  return { counted: counted.length, changes, skipped: items.length - counted.length };
}

/** First index after `from` (wrapping, `from` excluded) whose item has no valid count; null when none. */
export function nextUncounted(items: readonly InventoryItem[], counts: Counts, from: number): number | null {
  for (let step = 1; step < items.length; step++) {
    const index = (from + step) % items.length;
    if (countedValue(counts[items[index]?.itemID ?? ""]) === null) return index;
  }
  return null;
}
