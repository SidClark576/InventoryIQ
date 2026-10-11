import { useEffect, useMemo } from "react";
import { Link } from "react-router";
import { useInventory } from "@/app/inventory-store";
import { SHEET_LINK_STATE, useSheetParams } from "@/app/use-sheet-params";
import { ActivityRow } from "@/components/activity-row";
import { TEXT_LINK_CLASS } from "@/components/text-link";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { timeAgo } from "@/lib/activity";
import { cn } from "@/lib/utils";

const SHOWN = 8;

export function RecentActivity() {
  const { transactions, txStatus, txError, loadTransactions, items } = useInventory();
  const { itemHref } = useSheetParams();

  useEffect(() => {
    void loadTransactions();
  }, [loadTransactions]);

  const known = useMemo(() => new Set(items.map((item) => item.itemID)), [items]);
  const rows = transactions.slice(0, SHOWN);
  const now = new Date();

  if (txStatus === "error") {
    return (
      <div className="flex flex-col items-start gap-2 px-5 py-6">
        <p className="text-sm text-destructive">{txError}</p>
        <Button type="button" variant="outline" size="sm" onClick={() => void loadTransactions(true)}>
          Try again
        </Button>
      </div>
    );
  }
  if (txStatus !== "ready" && rows.length === 0) {
    return (
      <div className="flex flex-col gap-3 px-5 py-4">
        {Array.from({ length: 4 }, (_, index) => (
          <Skeleton key={index} className="h-8 w-full" />
        ))}
      </div>
    );
  }
  if (rows.length === 0) {
    return <p className="px-5 py-8 text-sm text-muted-foreground">No stock changes yet.</p>;
  }
  return (
    <ul id="recent-activity" className="divide-y divide-border px-5">
      {rows.map((tx, index) => (
        <ActivityRow
          key={tx.transactionID ?? `${tx.createdAt}-${index}`}
          tx={tx}
          time={timeAgo(tx.createdAt, now)}
          name={
            tx.itemID && known.has(tx.itemID) ? (
              <Link to={itemHref(tx.itemID)} state={SHEET_LINK_STATE} className={cn(TEXT_LINK_CLASS, "no-underline hover:underline")}>
                {tx.itemName || "Item"}
              </Link>
            ) : (
              tx.itemName || "Item"
            )
          }
        />
      ))}
    </ul>
  );
}
