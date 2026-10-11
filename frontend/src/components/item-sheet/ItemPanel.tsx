import { useState } from "react";
import { TrashIcon } from "@phosphor-icons/react";
import type { InventoryItem } from "@/api";
import { useStockActions } from "@/app/use-stock-actions";
import { LevelGauge } from "@/components/charts/level-gauge";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { priceOf, quantityOf, stockLevelOf, thresholdOf } from "@/lib/dashboardStats";
import { formatMoney } from "@/lib/format";
import { AdjustControls } from "./AdjustControls";
import { ItemEditForm } from "./ItemEditForm";
import { ItemHistory } from "./ItemHistory";

type ItemPanelProps = {
  item: InventoryItem;
  onDeleted: () => void;
};

export function ItemPanel({ item, onDeleted }: ItemPanelProps) {
  const { deleteItems } = useStockActions();
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const quantity = quantityOf(item);
  const threshold = thresholdOf(item);
  const level = stockLevelOf(item);
  const itemID = item.itemID ?? "";

  async function remove() {
    setDeleting(true);
    const deleted = await deleteItems([item]);
    setDeleting(false);
    setConfirming(false);
    if (deleted.length) onDeleted();
  }

  return (
    <>
      <SheetHeader className="gap-1 pr-14 pb-2">
        <SheetDescription className="text-xs">{item.category || "Uncategorized"}</SheetDescription>
        <SheetTitle className="text-xl leading-tight font-semibold text-balance">{item.name || "Untitled item"}</SheetTitle>
      </SheetHeader>
      <div className="flex flex-col gap-6 px-6 pb-8">
        <div className="flex flex-col gap-3 rounded-3xl bg-muted/60 p-5">
          <div className="flex items-end justify-between gap-3">
            <p className="flex items-baseline gap-2">
              <span id="item-quantity" className="font-heading text-6xl leading-none font-semibold tracking-tight tabular-nums">
                {quantity}
              </span>
              <span className="text-sm text-muted-foreground">on hand</span>
            </p>
            <StatusBadge level={level} />
          </div>
          <LevelGauge quantity={quantity} threshold={threshold} level={level} className="bg-background" />
          <dl className="flex gap-6 text-xs text-muted-foreground">
            <div>
              <dt>Alert at</dt>
              <dd className="text-sm font-medium text-foreground tabular-nums">{threshold}</dd>
            </div>
            <div>
              <dt>Unit price</dt>
              <dd className="text-sm font-medium text-foreground tabular-nums">{formatMoney(priceOf(item))}</dd>
            </div>
            <div>
              <dt>Value</dt>
              <dd className="text-sm font-medium text-foreground tabular-nums">
                {formatMoney(priceOf(item) * quantity)}
              </dd>
            </div>
          </dl>
        </div>

        <AdjustControls item={item} />
        <Separator />
        <ItemEditForm item={item} />
        <Separator />
        {itemID ? <ItemHistory itemID={itemID} /> : null}
        <Separator />
        <Button
          type="button"
          variant="destructive"
          className="self-start"
          onClick={() => setConfirming(true)}
        >
          <TrashIcon />
          Delete item
        </Button>
      </div>
      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        title="Delete this item?"
        description={`${item.name || "This item"} moves to deleted items. You can restore it for 30 days.`}
        confirmLabel="Delete"
        busy={deleting}
        onConfirm={() => void remove()}
      />
    </>
  );
}
