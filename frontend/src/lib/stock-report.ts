import type { InventoryItem } from "@/api";
// Relative .ts imports so node:test can load this module (no `@/` resolution there).
import { deltaOf, type Transaction } from "./activity.ts";
import { priceOf, quantityOf } from "./dashboardStats.ts";

/** One line of the paper "Inventory of Stocks" sheet. */
export type ReportRow = { name: string; size: string; price: number; starting: number; stockIn: number; now: number };
export type ReportGroup = { category: string; rows: ReportRow[] };

export const REPORT_HEADERS = ["Item", "Size", "Price", "Starting stock", "Stock in", "Stock now"] as const;

const UNCATEGORIZED = "Uncategorized";

/** "YYYY-MM-DD" in local time (the value an <input type="date"> uses). */
export function localDate(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

export function defaultStartDate(now: Date = new Date()): string {
  return `${localDate(now).slice(0, 8)}01`;
}

/** Deliveries only: "Received …" stock-ins and an item's first quantity. Count fixes are corrections, not stock in. */
export function isRestock(tx: Transaction): boolean {
  if (tx.changeType === "create") return true;
  return tx.changeType === "stock_in" && /^\s*received\b/i.test(tx.notes ?? "");
}

function rowFor(item: InventoryItem, since: readonly Transaction[]): ReportRow {
  const now = quantityOf(item);
  const sum = (txs: readonly Transaction[]) => txs.reduce((total, tx) => total + deltaOf(tx), 0);
  return {
    name: item.name ?? "",
    size: item.description ?? "",
    price: priceOf(item),
    // No clamp: a negative start means the log and the shelf disagree, which the owner should see.
    starting: now - sum(since),
    stockIn: sum(since.filter(isRestock)),
    now,
  };
}

export function buildStockReport(
  items: readonly InventoryItem[],
  txs: readonly Transaction[],
  start: Date,
): ReportGroup[] {
  const since = txs.filter((tx) => new Date(tx.createdAt ?? "").getTime() >= start.getTime());
  const groups = new Map<string, ReportRow[]>();
  for (const item of items) {
    const category = item.category || UNCATEGORIZED;
    const rows = groups.get(category) ?? [];
    rows.push(rowFor(item, item.itemID ? since.filter((tx) => tx.itemID === item.itemID) : []));
    groups.set(category, rows);
  }
  const rank = (category: string) => (category === UNCATEGORIZED ? 1 : 0);
  return [...groups]
    .sort(([a], [b]) => rank(a) - rank(b) || a.localeCompare(b))
    .map(([category, rows]) => ({ category, rows: rows.sort((a, b) => a.name.localeCompare(b.name)) }));
}
