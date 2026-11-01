import { formatMoney } from "@/lib/format";
import { REPORT_HEADERS } from "@/lib/stock-report";
import type { StockReport } from "./ReportDialog";

type ReportProps = { report: StockReport; storeName: string };

const longDate = (date: Date) => date.toLocaleDateString(undefined, { year: "numeric", month: "long", day: "numeric" });

/** The paper "Inventory of Stocks" sheet, id-less so the preview and the printout can both render it. Styled by `.report-sheet` in index.css. */
export function ReportTable({ report: { groups, start, asOf, selected }, storeName }: ReportProps) {
  return (
    <>
      <h1 className="print-title">{storeName}</h1>
      <p className="print-subtitle">Inventory of Stocks{selected ? " · Selected items" : ""}</p>
      <p className="print-meta">
        As of {longDate(asOf)} · from {longDate(start)}
      </p>
      <table>
        <thead>
          <tr>
            {REPORT_HEADERS.map((header, index) => (
              <th key={header} className={index >= 3 ? "num" : undefined}>
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {groups.flatMap((group) => [
            <tr key={`group-${group.category}`} className="print-category">
              <th colSpan={REPORT_HEADERS.length} scope="colgroup">
                {group.category.toUpperCase()}:
              </th>
            </tr>,
            ...group.rows.map((row, index) => (
              <tr key={`${group.category}-${row.name}-${index}`}>
                <td>{row.name}</td>
                <td>{row.category}</td>
                <td>{row.description}</td>
                <td className="num">{formatMoney(row.price)}</td>
                <td className="num">{row.starting}</td>
                <td className="num">{row.stockIn}</td>
                <td className="num">{row.now}</td>
              </tr>
            )),
          ])}
        </tbody>
      </table>
    </>
  );
}

/** What actually prints. Hidden on screen; index.css shows it when <html data-iq-print="inventory"> prints. */
export function PrintReport(props: ReportProps) {
  return (
    <section id="print-section" className="report-sheet" data-print-region aria-hidden>
      <ReportTable {...props} />
    </section>
  );
}
