import { formatMoney } from "@/lib/format";
import { REPORT_HEADERS, type ReportGroup } from "@/lib/stock-report";

type PrintReportProps = { groups: readonly ReportGroup[]; start: Date; asOf: Date; storeName: string };

const longDate = (date: Date) => date.toLocaleDateString(undefined, { year: "numeric", month: "long", day: "numeric" });

/** The paper "Inventory of Stocks" sheet. Hidden on screen; index.css shows it when <html data-iq-print="inventory"> prints. */
export function PrintReport({ groups, start, asOf, storeName }: PrintReportProps) {
  return (
    <section id="print-section" data-print-region aria-hidden>
      <h1 className="print-title">{storeName}</h1>
      <p className="print-subtitle">Inventory of Stocks</p>
      <p className="print-meta">
        As of {longDate(asOf)} · from {longDate(start)}
      </p>
      <table id="print-table">
        <thead>
          <tr>
            {REPORT_HEADERS.map((header, index) => (
              <th key={header} className={index >= 2 ? "num" : undefined}>
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
                <td>{row.size}</td>
                <td className="num">{formatMoney(row.price)}</td>
                <td className="num">{row.starting}</td>
                <td className="num">{row.stockIn}</td>
                <td className="num">{row.now}</td>
              </tr>
            )),
          ])}
        </tbody>
      </table>
    </section>
  );
}
