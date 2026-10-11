import type { InventoryItem } from "@/api";
import { quantityOf } from "@/lib/dashboardStats";

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
