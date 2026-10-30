import { toCsv } from "@/lib/csv";
import { localDate, REPORT_HEADERS, type ReportGroup } from "@/lib/stock-report";

/** The paper sheet as CSV: a category heading row ("CAN GOODS:") before each group's rows. */
export function downloadReportCsv(groups: readonly ReportGroup[], asOf: Date, suffix = ""): void {
  const csv = toCsv(
    REPORT_HEADERS,
    groups.flatMap((group) => [
      [`${group.category.toUpperCase()}:`, "", "", "", "", "", ""],
      ...group.rows.map((row) => [row.name, row.category, row.description, row.price, row.starting, row.stockIn, row.now]),
    ]),
  );
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = `panindo_stock_report_${localDate(asOf)}${suffix}.csv`;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}
