import { useEffect, useMemo } from "react";
import { Link, useSearchParams } from "react-router";
import { ArrowClockwiseIcon, MagnifyingGlassIcon, PulseIcon } from "@phosphor-icons/react";
import { useInventory } from "@/app/inventory-store";
import { SHEET_LINK_STATE, useSheetParams } from "@/app/use-sheet-params";
import { ActivityRow } from "@/components/activity-row";
import { ItemSheetHost } from "@/components/item-sheet/ItemSheetHost";
import { PageHeader } from "@/components/page-header";
import { TEXT_LINK_CLASS } from "@/components/text-link";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import {
  ACTIVITY_FILTERS,
  groupByDay,
  matchesFilter,
  matchesSearch,
  timeOfDay,
  type ActivityFilter,
} from "@/lib/activity";
import { cn } from "@/lib/utils";

function filterFrom(value: string | null): ActivityFilter {
  return ACTIVITY_FILTERS.some((option) => option.value === value) ? (value as ActivityFilter) : "all";
}

export function ActivityScreen() {
  const { transactions, txStatus, txError, loadTransactions, items } = useInventory();
  const { itemHref } = useSheetParams();
  const [params, setParams] = useSearchParams();
  const filter = filterFrom(params.get("type"));
  const query = params.get("q") ?? "";

  useEffect(() => {
    document.title = "Activity | InventoryIQ";
    void loadTransactions();
  }, [loadTransactions]);

  function setParam(key: string, value: string, fallback: string) {
    const next = new URLSearchParams(params);
    if (value && value !== fallback) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  }

  const known = useMemo(() => new Set(items.map((item) => item.itemID)), [items]);
  const rows = useMemo(
    () => transactions.filter((tx) => matchesFilter(tx, filter) && matchesSearch(tx, query)),
    [transactions, filter, query],
  );
  const groups = useMemo(() => groupByDay(rows), [rows]);
  const loading = txStatus === "idle" || (txStatus === "loading" && transactions.length === 0);

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-5">
      <PageHeader
        title="Activity"
        description="Recent stock changes across your organization, newest first."
        actions={
          <Button
            type="button"
            variant="outline"
            disabled={txStatus === "loading"}
            onClick={() => void loadTransactions(true)}
          >
            <ArrowClockwiseIcon className={cn(txStatus === "loading" && "animate-spin")} />
            Refresh
          </Button>
        }
      />

      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <ToggleGroup
          aria-label="Filter activity"
          value={[filter]}
          onValueChange={(value) => setParam("type", value[0] ?? "all", "all")}
          variant="outline"
          size="sm"
          spacing={1}
          className="flex-wrap"
        >
          {ACTIVITY_FILTERS.map((option) => (
            <ToggleGroupItem
              key={option.value}
              value={option.value}
              className="aria-pressed:border-foreground/70 aria-pressed:bg-foreground aria-pressed:text-background"
            >
              {option.label}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
        <div className="relative w-full lg:w-72">
          <MagnifyingGlassIcon className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            id="tx-search"
            type="search"
            value={query}
            onChange={(event) => setParam("q", event.target.value, "")}
            placeholder="Search items or notes"
            aria-label="Search activity"
            className="pl-9"
          />
        </div>
      </div>

      <p id="tx-count" className="-mt-1 text-xs text-muted-foreground tabular-nums" aria-live="polite">
        {loading ? "Loading…" : `${rows.length} of the latest ${transactions.length} changes`}
      </p>

      {txStatus === "error" ? (
        <div role="alert" className="flex flex-wrap items-center gap-3 rounded-3xl border border-destructive/30 bg-destructive/5 px-5 py-4 text-sm">
          <span className="text-destructive">{txError}</span>
          <Button type="button" variant="outline" size="sm" onClick={() => void loadTransactions(true)}>
            Try again
          </Button>
        </div>
      ) : loading ? (
        <div className="flex flex-col gap-3 rounded-3xl border border-border bg-card p-5">
          {Array.from({ length: 6 }, (_, index) => (
            <Skeleton key={index} className="h-9 w-full" />
          ))}
        </div>
      ) : groups.length === 0 ? (
        <div className="flex flex-col items-center gap-2 rounded-3xl border border-dashed border-border px-6 py-14 text-center">
          <PulseIcon className="size-8 text-muted-foreground" />
          <p className="font-medium">{transactions.length ? "Nothing matches those filters" : "No stock changes yet"}</p>
          <p className="text-sm text-muted-foreground">
            {transactions.length ? "Try another filter or clear the search." : "Changes show up here as your team adjusts stock."}
          </p>
        </div>
      ) : (
        <div id="tx-body" className="flex flex-col gap-5">
          {groups.map((group) => (
            <section key={group.key} aria-labelledby={`day-${group.key}`}>
              <h2
                id={`day-${group.key}`}
                className="sticky top-14 z-10 bg-background/90 py-1.5 text-xs font-semibold text-muted-foreground backdrop-blur-sm md:top-0"
              >
                {group.label}
              </h2>
              <ul className="divide-y divide-border rounded-3xl border border-border bg-card px-5">
                {group.rows.map((tx, index) => (
                  <ActivityRow
                    key={tx.transactionID ?? `${tx.createdAt}-${index}`}
                    tx={tx}
                    time={timeOfDay(tx.createdAt)}
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
            </section>
          ))}
        </div>
      )}

      <ItemSheetHost />
    </div>
  );
}
