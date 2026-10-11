import { Link } from "react-router";
import { CaretRightIcon } from "@phosphor-icons/react";
import type { InventoryItem } from "@/api";
import { SHEET_LINK_STATE } from "@/app/use-sheet-params";
import { LevelGauge } from "@/components/charts/level-gauge";
import { LEVEL_LABEL, StatusBadge } from "@/components/status-badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { quantityOf, stockLevelOf, thresholdOf } from "@/lib/dashboardStats";
import { cn } from "@/lib/utils";
import { countedValue, type Counts } from "./count";
import type { StockGroup } from "./stock-view";

type ItemHref = (itemID: string) => { pathname: string; search: string };

type StockTableProps = {
  groups: readonly StockGroup[];
  collapsed: ReadonlySet<string>;
  onToggleGroup: (key: string) => void;
  selected: ReadonlySet<string>;
  onSelect: (itemIDs: readonly string[], checked: boolean) => void;
  counting: boolean;
  counts: Counts;
  onCount: (itemID: string, value: string) => void;
  itemHref: ItemHref;
};

const HEAD = "h-10 px-3 text-left align-middle text-xs font-medium whitespace-nowrap text-muted-foreground";
const CELL = "px-3 py-3 align-middle";

export function StockTable({
  groups,
  collapsed,
  onToggleGroup,
  selected,
  onSelect,
  counting,
  counts,
  onCount,
  itemHref,
}: StockTableProps) {
  const visibleIDs = groups
    .filter((group) => counting || !collapsed.has(group.key))
    .flatMap((group) => group.items.flatMap((item) => (item.itemID ? [item.itemID] : [])));
  const allSelected = visibleIDs.length > 0 && visibleIDs.every((id) => selected.has(id));
  const someSelected = !allSelected && visibleIDs.some((id) => selected.has(id));
  const columns = 5;

  return (
    <div className="overflow-hidden rounded-3xl border border-border bg-card">
      <table id="inventory-table" className="w-full border-collapse text-sm">
        <thead className="border-b border-border">
          <tr>
            <th className={cn(HEAD, counting ? "w-2 p-0" : "w-11 pr-0 pl-4")}>
              {counting ? (
                <span className="sr-only">Row</span>
              ) : (
                <Checkbox
                  aria-label="Select all shown"
                  className="data-indeterminate:border-primary data-indeterminate:bg-primary data-indeterminate:before:h-0.5 data-indeterminate:before:w-2 data-indeterminate:before:rounded-full data-indeterminate:before:bg-primary-foreground data-indeterminate:[&_svg]:hidden"
                  checked={allSelected}
                  indeterminate={someSelected}
                  disabled={visibleIDs.length === 0}
                  onCheckedChange={(checked) => onSelect(visibleIDs, checked)}
                />
              )}
            </th>
            <th className={cn(HEAD, "w-full")}>Item</th>
            <th className={cn(HEAD, "w-16 text-right sm:w-24", counting && "hidden sm:table-cell")}>
              {counting ? "Expected" : "On hand"}
            </th>
            <th className={cn(HEAD, counting ? "w-24 text-right" : "hidden min-w-44 md:table-cell lg:min-w-56")}>
              {counting ? "Counted" : "Level"}
            </th>
            <th className={cn(HEAD, counting ? "w-24 text-right sm:w-28" : "hidden w-28 sm:table-cell")}>
              {counting ? "Difference" : "Status"}
            </th>
          </tr>
        </thead>
        {groups.map((group) => {
          const open = counting || !collapsed.has(group.key);
          return (
            <tbody key={group.key} className="border-b border-border last:border-b-0">
              <tr>
                <th scope="rowgroup" colSpan={columns} className="bg-muted/40 p-0 text-left">
                  <button
                    type="button"
                    aria-expanded={open}
                    disabled={counting}
                    onClick={() => onToggleGroup(group.key)}
                    className="flex h-10 w-full items-center gap-2 px-4 text-sm font-semibold outline-none hover:bg-muted/60 focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:ring-inset disabled:cursor-default disabled:hover:bg-transparent"
                  >
                    <CaretRightIcon
                      aria-hidden
                      className={cn("size-3.5 text-muted-foreground transition-transform", open && "rotate-90")}
                    />
                    {group.title}
                    <span
                      className={cn(
                        "rounded-full px-2 py-0.5 text-xs tabular-nums",
                        group.tone === "attention" ? "bg-warning/15 text-foreground" : "bg-muted text-muted-foreground",
                      )}
                    >
                      {group.items.length}
                    </span>
                  </button>
                </th>
              </tr>
              {open
                ? group.items.map((item) => (
                    <StockRow
                      key={item.itemID ?? item.name}
                      item={item}
                      selected={Boolean(item.itemID && selected.has(item.itemID))}
                      onSelect={onSelect}
                      counting={counting}
                      counted={item.itemID ? counts[item.itemID] ?? "" : ""}
                      onCount={onCount}
                      itemHref={itemHref}
                    />
                  ))
                : null}
            </tbody>
          );
        })}
      </table>
    </div>
  );
}

type StockRowProps = {
  item: InventoryItem;
  selected: boolean;
  onSelect: (itemIDs: readonly string[], checked: boolean) => void;
  counting: boolean;
  counted: string;
  onCount: (itemID: string, value: string) => void;
  itemHref: ItemHref;
};

function Variance({ expected, counted }: { expected: number; counted: number | null }) {
  if (counted === null) {
    return (
      <span className="text-xs whitespace-nowrap text-muted-foreground">
        <span aria-hidden className="sm:hidden">—</span>
        <span className="sr-only sm:not-sr-only">Not counted</span>
      </span>
    );
  }
  const diff = counted - expected;
  if (diff === 0) return <span className="text-xs whitespace-nowrap text-muted-foreground">Matches</span>;
  return (
    <span className={cn("font-semibold tabular-nums", diff > 0 ? "text-success" : "text-destructive")}>
      {diff > 0 ? `+${diff}` : `−${Math.abs(diff)}`}
    </span>
  );
}

function StockRow({ item, selected, onSelect, counting, counted, onCount, itemHref }: StockRowProps) {
  const id = item.itemID ?? "";
  const name = item.name || "Untitled item";
  const quantity = quantityOf(item);
  const threshold = thresholdOf(item);
  const level = stockLevelOf(item);

  return (
    <tr
      data-item-id={id || undefined}
      className={cn("border-t border-border/70 transition-colors", selected ? "bg-primary/6" : "hover:bg-muted/40")}
    >
      <td className={cn(CELL, counting ? "p-0" : "pr-0 pl-4")}>
        {counting ? null : (
          <Checkbox
            aria-label={`Select ${name}`}
            checked={selected}
            disabled={!id}
            onCheckedChange={(checked) => onSelect([id], checked)}
          />
        )}
      </td>
      {/* max-w-0 lets the name column take the remaining width and truncate (auto table layout). */}
      <td className={cn(CELL, "max-w-0")}>
        <Link
          to={itemHref(id)} state={SHEET_LINK_STATE}
          className="block truncate rounded-sm font-medium outline-none hover:underline focus-visible:ring-[3px] focus-visible:ring-ring/50"
        >
          {name}
        </Link>
        <span className="block truncate text-xs text-muted-foreground">
          {item.category || "Uncategorized"}
          {counting ? <span className="sm:hidden"> · expected {quantity}</span> : null}
          {!counting && level !== "ok" ? (
            <span className={cn("font-medium sm:hidden", level === "out" ? "text-destructive" : "text-warning")}>
              {" · "}
              {LEVEL_LABEL[level]}
            </span>
          ) : null}
        </span>
        {counting ? null : (
          <LevelGauge quantity={quantity} threshold={threshold} level={level} className="mt-2 w-24 min-w-0 md:hidden" />
        )}
      </td>
      <td className={cn(CELL, "text-right", counting && "hidden sm:table-cell")}>
        {counting ? (
          <span className="font-semibold tabular-nums">{quantity}</span>
        ) : (
          <Link
            to={itemHref(id)} state={SHEET_LINK_STATE}
            aria-label={`${name}: ${quantity} on hand. Open item`}
            className="inline-flex h-8 min-w-10 items-center justify-end rounded-xl px-2 text-base font-semibold tabular-nums outline-none hover:bg-muted focus-visible:ring-[3px] focus-visible:ring-ring/50"
          >
            {quantity}
          </Link>
        )}
      </td>
      <td className={cn(CELL, counting ? "text-right" : "hidden md:table-cell")}>
        {counting ? (
          <Input
            type="number"
            min={0}
            step={1}
            inputMode="numeric"
            aria-label={`Counted ${name}`}
            placeholder={String(quantity)}
            value={counted}
            onChange={(event) => onCount(id, event.target.value)}
            className="ml-auto h-8 w-20 text-right tabular-nums"
          />
        ) : (
          <div className="flex flex-col gap-1.5">
            <LevelGauge quantity={quantity} threshold={threshold} level={level} />
            <span className="text-xs text-muted-foreground tabular-nums">alert at {threshold}</span>
          </div>
        )}
      </td>
      <td className={cn(CELL, counting ? "text-right" : "hidden sm:table-cell")}>
        {counting ? (
          <Variance expected={quantity} counted={countedValue(counted)} />
        ) : (
          <StatusBadge level={level} />
        )}
      </td>
    </tr>
  );
}
