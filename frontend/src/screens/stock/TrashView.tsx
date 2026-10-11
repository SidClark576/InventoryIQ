import { useEffect, useState } from "react";
import { ArrowCounterClockwiseIcon, ArrowLeftIcon, TrashIcon } from "@phosphor-icons/react";
import { toast } from "sonner";
import { getDeletedItems, type InventoryItem } from "@/api";
import { useOrgShell } from "@/app/AppLayout";
import { useStockActions } from "@/app/use-stock-actions";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { quantityOf } from "@/lib/dashboardStats";
import { plural } from "@/lib/format";
import { errorText } from "@/lib/errors";

const RESTORE_DAYS = 30;
const DAY_MS = 86_400_000;

function daysLeft(deletedAt: string | undefined): number | null {
  if (!deletedAt) return null;
  const at = new Date(deletedAt).getTime();
  if (Number.isNaN(at)) return null;
  return Math.max(0, RESTORE_DAYS - Math.floor((Date.now() - at) / DAY_MS));
}

export function TrashView({ onBack }: { onBack: () => void }) {
  const { orgEpoch, canEdit } = useOrgShell();
  const { restoreItems } = useStockActions();
  const [rows, setRows] = useState<InventoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [restoring, setRestoring] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    void getDeletedItems()
      .then((items) => {
        if (!cancelled) setRows(items);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(errorText(err, "Couldn't load deleted items"));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [orgEpoch]);

  async function restore(item: InventoryItem) {
    if (!item.itemID) return;
    setRestoring(item.itemID);
    const restored = await restoreItems([item]);
    setRestoring(null);
    if (restored.length === 0) return;
    setRows((prev) => prev.filter((row) => row.itemID !== item.itemID));
    toast.success(`Restored ${item.name || "item"}`);
  }

  return (
    <section aria-labelledby="trash-heading" className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <Button type="button" variant="ghost" size="sm" onClick={onBack}>
          <ArrowLeftIcon />
          Back to stock
        </Button>
        <h2 id="trash-heading" className="font-heading text-lg font-semibold">
          Deleted items
        </h2>
        <span className="text-sm text-muted-foreground">Restorable for {RESTORE_DAYS} days</span>
      </div>
      <div className="overflow-hidden rounded-3xl border border-border bg-card">
        {loading ? (
          <div className="flex flex-col gap-3 p-5">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        ) : error ? (
          <p role="alert" className="p-5 text-sm text-destructive">
            {error}
          </p>
        ) : rows.length === 0 ? (
          <div className="flex flex-col items-center gap-2 px-6 py-14 text-center">
            <TrashIcon className="size-8 text-muted-foreground" />
            <p className="font-medium">No deleted items</p>
            <p className="text-sm text-muted-foreground">Deleted items wait here for {RESTORE_DAYS} days.</p>
          </div>
        ) : (
          <ul id="inventory-body" className="divide-y divide-border">
            {rows.map((item) => {
              const left = daysLeft(item.deletedAt);
              return (
                <li key={item.itemID ?? item.name} className="flex items-center gap-3 px-5 py-3">
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium text-muted-foreground line-through decoration-muted-foreground/50">
                      {item.name || "Untitled item"}
                    </p>
                    <p className="text-xs text-muted-foreground tabular-nums">
                      {item.category || "Uncategorized"} · {quantityOf(item)} on hand
                      {left !== null ? ` · ${plural(left, "day")} left` : ""}
                    </p>
                  </div>
                  {canEdit ? (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={restoring !== null}
                      onClick={() => void restore(item)}
                    >
                      <ArrowCounterClockwiseIcon />
                      {restoring === item.itemID ? "Restoring…" : "Restore"}
                    </Button>
                  ) : null}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </section>
  );
}
