import { useState } from "react";
import { toast } from "sonner";
import { useInventory } from "@/app/inventory-store";
import { useStockActions } from "@/app/use-stock-actions";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { priceOf } from "@/lib/dashboardStats";
import { formatMoney, plural } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { CountChange } from "./count";

type CountReviewDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  counted: number;
  total: number;
  changes: readonly CountChange[];
  /** Called after the count is applied (or confirmed with no changes). */
  onFinished: () => void;
};

/** Lists only the rows that changed, then sends one PUT per item with the note "Count fix". */
export function CountReviewDialog({ open, onOpenChange, counted, total, changes, onFinished }: CountReviewDialogProps) {
  const { setQuantity } = useStockActions();
  const { reloadItems } = useInventory();
  const [progress, setProgress] = useState<number | null>(null);
  const busy = progress !== null;
  const net = changes.reduce((sum, change) => sum + (change.counted - change.expected) * priceOf(change.item), 0);

  async function apply() {
    if (changes.length === 0) {
      toast.success("Count saved. Everything matched.");
      onFinished();
      return;
    }
    const failed: string[] = [];
    for (const [index, change] of changes.entries()) {
      setProgress(index + 1);
      const saved = await setQuantity(change.item, change.counted, "Count fix", { silent: true });
      if (!saved) failed.push(change.item.name || "Item");
    }
    setProgress(null);
    const updated = changes.length - failed.length;
    if (updated) toast.success(`Count saved. ${plural(updated, "item")} updated.`);
    if (failed.length) {
      toast.error(`${plural(failed.length, "item")} didn't save`, {
        description: `${failed.join(", ")}. Loaded the latest stock; count those again.`,
      });
      void reloadItems();
    }
    onFinished();
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!busy) onOpenChange(next);
      }}
    >
      <DialogContent className="max-h-[90svh] grid-rows-[auto_minmax(0,1fr)_auto] sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Review count</DialogTitle>
          <DialogDescription>
            {counted} of {total} counted.{" "}
            {total - counted > 0 ? `${plural(total - counted, "item")} not counted stay as they are.` : "Every item was counted."}
          </DialogDescription>
        </DialogHeader>
        <div className="flex min-h-0 flex-col gap-4">
          <dl className="grid grid-cols-3 gap-2 rounded-2xl bg-muted/60 p-3 text-center">
            <div>
              <dt className="text-xs text-muted-foreground">Changes</dt>
              <dd className="text-lg font-semibold tabular-nums">{changes.length}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Matched</dt>
              <dd className="text-lg font-semibold tabular-nums">{counted - changes.length}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Value change</dt>
              <dd className={cn("text-lg font-semibold tabular-nums", net < 0 && "text-destructive")}>
                {net < 0 ? "−" : "+"}
                {formatMoney(Math.abs(net))}
              </dd>
            </div>
          </dl>
          {changes.length ? (
            <ul id="count-review-list" className="min-h-0 divide-y divide-border overflow-y-auto rounded-2xl border border-border">
              {changes.map((change) => {
                const diff = change.counted - change.expected;
                return (
                  <li key={change.item.itemID} className="flex items-center gap-3 px-4 py-2.5 text-sm">
                    <span className="min-w-0 flex-1 truncate font-medium">{change.item.name}</span>
                    <span className="text-muted-foreground tabular-nums">
                      {change.expected} → <span className="text-foreground">{change.counted}</span>
                    </span>
                    <span
                      className={cn(
                        "w-12 text-right font-semibold tabular-nums",
                        diff > 0 ? "text-success" : "text-destructive",
                      )}
                    >
                      {diff > 0 ? `+${diff}` : `−${Math.abs(diff)}`}
                    </span>
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">Every counted item matches. Nothing will change.</p>
          )}
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" disabled={busy} onClick={() => onOpenChange(false)}>
            Keep counting
          </Button>
          <Button type="button" disabled={busy} onClick={() => void apply()}>
            {busy
              ? `Saving ${progress} of ${changes.length}…`
              : changes.length
                ? `Apply ${plural(changes.length, "change")}`
                : "Finish count"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
