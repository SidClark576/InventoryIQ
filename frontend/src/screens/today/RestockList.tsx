import { Link } from "react-router";
import { CheckCircleIcon, PlusIcon, SlidersHorizontalIcon } from "@phosphor-icons/react";
import type { InventoryItem } from "@/api";
import { SHEET_LINK_STATE, useSheetParams } from "@/app/use-sheet-params";
import { LevelGauge } from "@/components/charts/level-gauge";
import { TEXT_LINK_CLASS } from "@/components/text-link";
import { Button } from "@/components/ui/button";
import { quantityOf, stockLevelOf, thresholdOf } from "@/lib/dashboardStats";
import { cn } from "@/lib/utils";

const SHOWN = 8;

type RestockListProps = {
  queue: readonly InventoryItem[];
  /** Omitted for viewers, which hides Receive. */
  onReceive?: (item: InventoryItem) => void;
};

export function RestockList({ queue, onReceive }: RestockListProps) {
  const { itemHref } = useSheetParams();

  if (queue.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 px-6 py-12 text-center">
        <CheckCircleIcon className="size-10 text-success" weight="duotone" />
        <p className="font-medium">Nothing to restock</p>
        <p className="max-w-xs text-sm text-muted-foreground">
          Every item is above its low-stock alert. Items show up here as they run low.
        </p>
      </div>
    );
  }

  const shown = queue.slice(0, SHOWN);
  return (
    <>
      <ul id="restock-list" className="divide-y divide-border">
        {shown.map((item) => {
          const quantity = quantityOf(item);
          const threshold = thresholdOf(item);
          const level = stockLevelOf(item);
          const id = item.itemID ?? "";
          return (
            <li key={id || item.name} className="flex items-center gap-3 px-5 py-3.5 sm:gap-4">
              <span
                aria-hidden
                className={cn("h-9 w-1 shrink-0 rounded-full", level === "out" ? "bg-destructive" : "bg-warning")}
              />
              <div className="min-w-0 flex-1">
                <Link to={itemHref(id)} state={SHEET_LINK_STATE} className={cn(TEXT_LINK_CLASS, "block truncate no-underline hover:underline")}>
                  {item.name || "Untitled item"}
                </Link>
                <p className={cn("text-xs tabular-nums", level === "out" ? "text-destructive" : "text-warning")}>
                  {level === "out" ? "Out of stock" : `${quantity} left`}
                  <span className="text-muted-foreground"> · alert at {threshold}</span>
                </p>
              </div>
              <LevelGauge quantity={quantity} threshold={threshold} level={level} className="hidden w-28 sm:block" />
              <div className="flex shrink-0 gap-1.5">
                {onReceive ? (
                  <Button type="button" variant="outline" size="sm" onClick={() => onReceive(item)}>
                    <PlusIcon />
                    Receive
                  </Button>
                ) : null}
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  aria-label={`Adjust ${item.name || "item"}`}
                  render={<Link to={itemHref(id)} state={SHEET_LINK_STATE} />}
                  nativeButton={false}
                >
                  <SlidersHorizontalIcon />
                </Button>
              </div>
            </li>
          );
        })}
      </ul>
      {queue.length > SHOWN ? (
        <div className="border-t border-border px-5 py-3 text-sm">
          <Link to="/stock" className={TEXT_LINK_CLASS}>
            See all {queue.length} in Stock
          </Link>
        </div>
      ) : null}
    </>
  );
}
