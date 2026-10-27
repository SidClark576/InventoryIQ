import type { InventoryItem } from "@/api";
import { toCsv } from "@/lib/csv";

const CSV_HEADERS = [
  "itemID",
  "name",
  "category",
  "quantity",
  "price",
  "lowStockThreshold",
  "description",
  "barcode",
] as const;

export function downloadItemsCsv(items: readonly InventoryItem[], suffix = ""): void {
  const csv = toCsv(
    CSV_HEADERS,
    items.map((item) => CSV_HEADERS.map((header) => item[header])),
  );
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = `panindo_${new Date().toISOString().slice(0, 10)}${suffix}.csv`;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}
