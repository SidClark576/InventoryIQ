/** One row of GET /transactions (newest first, at most 200, no server-side filters). */
export type Transaction = {
  transactionID?: string;
  itemID?: string;
  itemName?: string;
  userID?: string;
  changeType?: string;
  quantityBefore?: number | string | null;
  quantityAfter?: number | string | null;
  quantityDelta?: number | string | null;
  notes?: string;
  createdAt?: string;
};

export type ActivityFilter = "all" | "in" | "out" | "waste" | "edits";

export const ACTIVITY_FILTERS: readonly { value: ActivityFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "in", label: "Stock in" },
  { value: "out", label: "Stock out" },
  { value: "waste", label: "Waste and damage" },
  { value: "edits", label: "Edits" },
];

const DAY_MS = 86_400_000;

function finite(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

export function parseTransactions(data: readonly unknown[]): Transaction[] {
  return data.filter((row): row is Transaction => Boolean(row) && typeof row === "object");
}

export function deltaOf(tx: Transaction): number {
  const delta = finite(tx.quantityDelta);
  if (delta !== null) return delta;
  const before = finite(tx.quantityBefore);
  const after = finite(tx.quantityAfter);
  return before !== null && after !== null ? after - before : 0;
}

export function quantityAfterOf(tx: Transaction): number | null {
  return finite(tx.quantityAfter);
}

/** Notes are free text; the stock sheet writes "Waste: 2" and "Damaged: 1". */
export function isWasteNote(notes: string | undefined): boolean {
  return /^\s*(waste|damaged)\b/i.test(notes ?? "");
}

export function matchesFilter(tx: Transaction, filter: ActivityFilter): boolean {
  const type = tx.changeType ?? "";
  if (filter === "all") return true;
  if (filter === "in") return type === "stock_in";
  if (filter === "out") return type === "stock_out";
  if (filter === "waste") return isWasteNote(tx.notes);
  return type === "create" || type === "update" || type === "delete";
}

export function matchesSearch(tx: Transaction, query: string): boolean {
  const needle = query.trim().toLowerCase();
  if (!needle) return true;
  return `${tx.itemName ?? ""} ${tx.notes ?? ""}`.toLowerCase().includes(needle);
}

export function historyFor(txs: readonly Transaction[], itemID: string): Transaction[] {
  return txs.filter((tx) => tx.itemID === itemID);
}

function startOfDay(date: Date): number {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
}

function parseDate(iso: string | undefined): Date | null {
  if (!iso) return null;
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function dayLabel(date: Date, now: Date = new Date()): string {
  const diff = Math.round((startOfDay(now) - startOfDay(date)) / DAY_MS);
  if (diff === 0) return "Today";
  if (diff === 1) return "Yesterday";
  return date.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
}

export type DayGroup = { key: string; label: string; rows: Transaction[] };

/** Groups rows by local calendar day, keeping input order (newest first). */
export function groupByDay(txs: readonly Transaction[], now: Date = new Date()): DayGroup[] {
  return txs.reduce<DayGroup[]>((groups, tx) => {
    const date = parseDate(tx.createdAt);
    const key = date ? String(startOfDay(date)) : "unknown";
    const last = groups[groups.length - 1];
    if (last && last.key === key) {
      return [...groups.slice(0, -1), { ...last, rows: [...last.rows, tx] }];
    }
    const label = date ? dayLabel(date, now) : "Unknown date";
    return [...groups, { key, label, rows: [tx] }];
  }, []);
}

export function timeOfDay(iso: string | undefined): string {
  const date = parseDate(iso);
  return date ? date.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" }) : "";
}

export function timeAgo(iso: string | undefined, now: Date = new Date()): string {
  const date = parseDate(iso);
  if (!date) return "";
  const minutes = Math.round((now.getTime() - date.getTime()) / 60_000);
  if (minutes < 1) return "now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}
