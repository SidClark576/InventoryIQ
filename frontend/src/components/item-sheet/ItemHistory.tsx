import { useEffect, useMemo } from "react";
import { useInventory } from "@/app/inventory-store";
import { ActivityRow } from "@/components/activity-row";
import { Skeleton } from "@/components/ui/skeleton";
import { historyFor, timeAgo } from "@/lib/activity";

const SHOWN = 8;

const CHANGE_LABEL: Record<string, string> = {
  stock_in: "Stock in",
  stock_out: "Stock out",
  create: "Added",
  delete: "Deleted",
  update: "Details changed",
};

/** Client-side filter of GET /transactions, which only returns the latest 200 changes overall. */
export function ItemHistory({ itemID }: { itemID: string }) {
  const { transactions, txStatus, txError, loadTransactions } = useInventory();

  useEffect(() => {
    void loadTransactions();
  }, [loadTransactions]);

  const rows = useMemo(() => historyFor(transactions, itemID).slice(0, SHOWN), [transactions, itemID]);
  const now = new Date();

  return (
    <section aria-labelledby="history-heading" className="flex flex-col gap-1">
      <h3 id="history-heading" className="text-sm font-semibold">
        Recent history
      </h3>
      <p className="text-xs text-muted-foreground">From the latest 200 changes across all items.</p>
      {txStatus === "loading" && rows.length === 0 ? (
        <div className="flex flex-col gap-2 pt-2">
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
        </div>
      ) : txStatus === "error" ? (
        <p className="pt-2 text-sm text-destructive">{txError}</p>
      ) : rows.length === 0 ? (
        <p className="pt-2 text-sm text-muted-foreground">No recent changes for this item.</p>
      ) : (
        <ul className="divide-y divide-border">
          {rows.map((tx, index) => (
            <ActivityRow
              key={tx.transactionID ?? `${tx.createdAt}-${index}`}
              tx={tx}
              name={CHANGE_LABEL[tx.changeType ?? ""] ?? "Changed"}
              time={timeAgo(tx.createdAt, now)}
            />
          ))}
        </ul>
      )}
    </section>
  );
}
