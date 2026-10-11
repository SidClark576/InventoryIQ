import { useCallback } from "react";
import { useSearchParams } from "react-router";
import type { InventoryItem } from "@/api";
import { restockQueue, stockLevelOf, type StockLevel } from "@/lib/dashboardStats";

export type StatusFilter = "all" | StockLevel;
export type Grouping = "status" | "category";

export type StockGroup = {
  key: string;
  title: string;
  tone: "attention" | "neutral";
  items: InventoryItem[];
};

const STATUS_FILTERS: readonly StatusFilter[] = ["all", "ok", "low", "out"];

function byName(a: InventoryItem, b: InventoryItem): number {
  return String(a.name ?? "").localeCompare(String(b.name ?? ""));
}

export function matchesQuery(item: InventoryItem, query: string): boolean {
  const needle = query.trim().toLowerCase();
  if (!needle) return true;
  return [item.name, item.category, item.barcode].some((field) =>
    String(field ?? "").toLowerCase().includes(needle),
  );
}

export function filterItems(items: readonly InventoryItem[], status: StatusFilter, query: string): InventoryItem[] {
  return items.filter(
    (item) => (status === "all" || stockLevelOf(item) === status) && matchesQuery(item, query),
  );
}

/** Status grouping answers "what next": Order now (out + low, most urgent first), then Healthy. */
export function groupItems(items: readonly InventoryItem[], grouping: Grouping): StockGroup[] {
  if (grouping === "status") {
    const groups: StockGroup[] = [
      { key: "order-now", title: "Order now", tone: "attention", items: restockQueue(items) },
      {
        key: "healthy",
        title: "Healthy",
        tone: "neutral",
        items: items.filter((item) => stockLevelOf(item) === "ok").sort(byName),
      },
    ];
    return groups.filter((group) => group.items.length > 0);
  }
  const byCategory = new Map<string, InventoryItem[]>();
  for (const item of items) {
    const category = item.category || "Uncategorized";
    byCategory.set(category, [...(byCategory.get(category) ?? []), item]);
  }
  return [...byCategory.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([category, rows]) => ({
      key: `cat:${category}`,
      title: category,
      tone: "neutral",
      items: [...rows].sort(byName),
    }));
}

/** Filters, grouping, search and the trash view live in the URL so they survive refresh and can be linked. */
export function useStockView() {
  const [params, setParams] = useSearchParams();
  const rawStatus = params.get("status");
  const status: StatusFilter = STATUS_FILTERS.includes(rawStatus as StatusFilter)
    ? (rawStatus as StatusFilter)
    : "all";
  const grouping: Grouping = params.get("group") === "category" ? "category" : "status";
  const query = params.get("q") ?? "";
  const trash = params.get("view") === "trash";

  const update = useCallback(
    (key: string, value: string | null) => {
      setParams(
        (current) => {
          const next = new URLSearchParams(current);
          if (value) next.set(key, value);
          else next.delete(key);
          return next;
        },
        { replace: true },
      );
    },
    [setParams],
  );

  return {
    status,
    grouping,
    query,
    trash,
    setStatus: (value: StatusFilter) => update("status", value === "all" ? null : value),
    setGrouping: (value: Grouping) => update("group", value === "status" ? null : value),
    setQuery: (value: string) => update("q", value || null),
    setTrash: (value: boolean) => update("view", value ? "trash" : null),
    clearFilters: () => {
      update("status", null);
      update("q", null);
    },
  };
}
