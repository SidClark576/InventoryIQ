import type { InventoryItem } from "@/api";
import { deltaOf, isWasteNote, type Transaction } from "./activity.ts";
import {
  daysUntilExpiry,
  deriveDashStats,
  EXPIRY_WINDOW_DAYS,
  priceOf,
  quantityOf,
  stockLevelOf,
  type DashStats,
} from "./dashboardStats.ts";

/** Insights reads this much history (GET /transactions?since=…). */
export const HISTORY_DAYS = 30;
export const RUNS_OUT_WITHIN_DAYS = 14;
const DAY_MS = 86_400_000;

export type RunningOut = { item: InventoryItem; daysLeft: number };
export type Expiring = { item: InventoryItem; days: number };
export type CategoryRisk = { category: string; atRisk: number; total: number; percent: number };

export type Insights = {
  stats: DashStats;
  /** Same formula as DailyAlert.py; null for an empty store. */
  health: number | null;
  /** Soonest first, within RUNS_OUT_WITHIN_DAYS. */
  runningOut: RunningOut[];
  /** In-stock items with enough history for an estimate (2+ uses across 3+ days). */
  estimated: number;
  expiring: Expiring[];
  notMoving: InventoryItem[];
  waste: { units: number; value: number; changes: number };
  categoryRisk: CategoryRisk[];
};

const isUndo = (tx: Transaction) => /^\s*undo\b/i.test(tx.notes ?? "");

/** Units sold or used: stock out that is not waste/damage, a count fix or an Undo. */
function isUse(tx: Transaction): boolean {
  return tx.changeType === "stock_out" && !isWasteNote(tx.notes) && !/^\s*count fix/i.test(tx.notes ?? "") && !isUndo(tx);
}

function startOfDay(ms: number): number {
  const date = new Date(ms);
  return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
}

/** Units used per day since the first use, or null without 2+ uses across 3+ calendar days. */
function usePerDay(txs: readonly Transaction[], now: Date): number | null {
  const uses = txs.filter(isUse);
  if (uses.length < 2) return null;
  const first = Math.min(...uses.map((tx) => Date.parse(tx.createdAt ?? "")));
  const days = Math.round((startOfDay(now.getTime()) - startOfDay(first)) / DAY_MS) + 1;
  if (days < 3) return null;
  // ponytail: an Undo stock_in is taken as undoing a sale; an undone waste row would net here too.
  const undone = txs.filter((tx) => isUndo(tx) && tx.changeType === "stock_in").reduce((sum, tx) => sum + deltaOf(tx), 0);
  const used = uses.reduce((sum, tx) => sum - deltaOf(tx), 0) - undone;
  return Math.max(0, used) / days;
}

function categoryRisk(items: readonly InventoryItem[]): CategoryRisk[] {
  const groups = new Map<string, { atRisk: number; total: number }>();
  for (const item of items) {
    const category = item.category || "Uncategorized";
    const group = groups.get(category) ?? { atRisk: 0, total: 0 };
    group.total += 1;
    if (stockLevelOf(item) !== "ok") group.atRisk += 1;
    groups.set(category, group);
  }
  return [...groups]
    .map(([category, { atRisk, total }]) => ({ category, atRisk, total, percent: Math.round((atRisk / total) * 100) }))
    .sort((a, b) => b.percent - a.percent || a.category.localeCompare(b.category));
}

/** Everything the Insights screen shows, from the item cache and the last HISTORY_DAYS of transactions. */
export function deriveInsights(items: readonly InventoryItem[], txs: readonly Transaction[], now = new Date()): Insights {
  const since = now.getTime() - HISTORY_DAYS * DAY_MS;
  const recent = txs.filter((tx) => tx.itemID && Date.parse(tx.createdAt ?? "") >= since);
  const byItem = new Map<string, Transaction[]>();
  for (const tx of recent) {
    const list = byItem.get(tx.itemID!) ?? [];
    list.push(tx);
    byItem.set(tx.itemID!, list);
  }
  const historyOf = (item: InventoryItem) => (item.itemID ? (byItem.get(item.itemID) ?? []) : []);
  const inStock = items.filter((item) => quantityOf(item) > 0);

  const estimates = inStock.flatMap((item) => {
    const perDay = usePerDay(historyOf(item), now);
    return perDay === null ? [] : [{ item, perDay }];
  });
  const runningOut = estimates
    .filter(({ perDay }) => perDay > 0)
    .map(({ item, perDay }) => ({ item, daysLeft: Math.ceil(quantityOf(item) / perDay) }))
    .filter(({ daysLeft }) => daysLeft <= RUNS_OUT_WITHIN_DAYS)
    .sort((a, b) => a.daysLeft - b.daysLeft);

  const expiring = inStock
    .map((item) => ({ item, days: daysUntilExpiry(item, now) }))
    .filter((row): row is Expiring => row.days !== null && row.days <= EXPIRY_WINDOW_DAYS)
    .sort((a, b) => a.days - b.days);

  const isYoung = (item: InventoryItem) =>
    (typeof item.createdAt === "string" && Date.parse(item.createdAt) > since) ||
    historyOf(item).some((tx) => tx.changeType === "create");
  const notMoving = inStock.filter(
    (item) => !isYoung(item) && !historyOf(item).some((tx) => tx.changeType === "stock_in" || tx.changeType === "stock_out"),
  );

  const prices = new Map(items.map((item) => [item.itemID, priceOf(item)]));
  const wasted = recent.filter((tx) => tx.changeType === "stock_out" && isWasteNote(tx.notes));
  const waste = wasted.reduce(
    (sum, tx) => ({
      units: sum.units - deltaOf(tx),
      value: sum.value - deltaOf(tx) * (prices.get(tx.itemID) ?? 0),
      changes: sum.changes + 1,
    }),
    { units: 0, value: 0, changes: 0 },
  );

  const stats = deriveDashStats(items);
  const health = items.length
    ? Math.max(0, Math.min(100, 100 - 25 * stats.outOfStockCount - 10 * stats.lowStockCount))
    : null;

  return { stats, health, runningOut, estimated: estimates.length, expiring, notMoving, waste, categoryRisk: categoryRisk(items) };
}
