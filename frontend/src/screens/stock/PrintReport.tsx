import type { InventoryItem } from "@/api";
import { deriveDashStats, priceOf, quantityOf, stockLevelOf } from "@/lib/dashboardStats";
import { LEVEL_LABEL } from "@/components/status-badge";
import { getUserEmail } from "@/session";

/** Hidden on screen; index.css shows it when <html data-iq-print="inventory"> prints. */
export function PrintReport({ items }: { items: readonly InventoryItem[] }) {
  const stats = deriveDashStats(items);
  const date = new Date().toLocaleDateString(undefined, { year: "numeric", month: "long", day: "numeric" });
  return (
    <section id="print-section" data-print-region aria-hidden>
      <h1 className="print-title">Panindo — Inventory Report</h1>
      <p className="print-meta">
        Generated: {date} | User: {getUserEmail()}
      </p>
      <table id="print-table">
        <thead>
          <tr>
            <th>Name</th>
            <th>Category</th>
            <th className="num">Qty</th>
            <th className="num">Price</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item, index) => (
            <tr key={item.itemID ?? index}>
              <td>{item.name}</td>
              <td>{item.category || "—"}</td>
              <td className="num">{quantityOf(item)}</td>
              <td className="num">${priceOf(item).toFixed(2)}</td>
              <td>{LEVEL_LABEL[stockLevelOf(item)]}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p id="print-summary" className="print-summary">
        <strong>Total Products:</strong> {stats.totalProducts} | <strong>In Stock:</strong>{" "}
        {stats.totalProducts - stats.lowStockCount - stats.outOfStockCount} | <strong>Low Stock:</strong>{" "}
        {stats.lowStockCount} | <strong>Out of Stock:</strong> {stats.outOfStockCount} |{" "}
        <strong>Total Value:</strong> ${stats.estimatedInventoryValue.toFixed(2)}
      </p>
    </section>
  );
}
