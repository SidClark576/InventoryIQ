import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router";
import { ArrowRightIcon, ChartLineUpIcon } from "@phosphor-icons/react";
import type { InventoryItem } from "@/api";
import { useInventory } from "@/app/inventory-store";
import { ItemSheetHost } from "@/components/item-sheet/ItemSheetHost";
import { TEXT_LINK_CLASS } from "@/components/text-link";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { deriveDashStats, restockQueue } from "@/lib/dashboardStats";
import { formatCompactMoney, plural } from "@/lib/format";
import { cn } from "@/lib/utils";
import { KpiStrip, type Kpi } from "./KpiStrip";
import { ReceiveDialog } from "./ReceiveDialog";
import { RecentActivity } from "./RecentActivity";
import { RestockList } from "./RestockList";

function greeting(now: Date): string {
  const hour = now.getHours();
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

function Panel({
  title,
  meta,
  children,
  className,
}: {
  title: string;
  meta?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  const id = `${title.toLowerCase().replace(/\s+/g, "-")}-heading`;
  return (
    <section aria-labelledby={id} className={cn("overflow-hidden rounded-3xl border border-border bg-card", className)}>
      <div className="flex items-baseline justify-between gap-3 px-5 pt-4 pb-2">
        <h2 id={id} className="font-heading text-base font-semibold">
          {title}
        </h2>
        {meta ? <div className="text-xs text-muted-foreground">{meta}</div> : null}
      </div>
      {children}
    </section>
  );
}

export function TodayScreen() {
  const { items, itemsStatus, itemsError, reloadItems } = useInventory();
  const [receiving, setReceiving] = useState<InventoryItem | null>(null);
  const now = new Date();

  useEffect(() => {
    document.title = "Today | InventoryIQ";
  }, []);

  const stats = useMemo(() => deriveDashStats(items), [items]);
  const queue = useMemo(() => restockQueue(items), [items]);
  const loading = itemsStatus === "idle" || itemsStatus === "loading";

  const kpis: Kpi[] = [
    { id: "stat-total", label: "Items", value: String(stats.totalProducts), to: "/stock" },
    { id: "stat-low", label: "Low", value: String(stats.lowStockCount), to: "/stock?status=low", tone: "warning" },
    { id: "stat-out", label: "Out", value: String(stats.outOfStockCount), to: "/stock?status=out", tone: "destructive" },
    { id: "stat-value", label: "Value on hand", value: formatCompactMoney(stats.estimatedInventoryValue), to: "/stock" },
  ];

  const status = queue.length
    ? `${plural(queue.length, "item")} need${queue.length === 1 ? "s" : ""} restocking`
    : "All stocked";

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-1">
        <p className="text-sm text-muted-foreground">
          {greeting(now)} ·{" "}
          {now.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" })}
        </p>
        {loading ? (
          <Skeleton className="h-9 w-72" />
        ) : (
          <h1 id="today-status" className="font-heading text-3xl font-semibold tracking-tight text-balance">
            {itemsStatus === "error" ? "Stock couldn't load" : status}
          </h1>
        )}
      </header>

      {itemsStatus === "error" ? (
        <div role="alert" className="flex flex-wrap items-center gap-3 rounded-3xl border border-destructive/30 bg-destructive/5 px-5 py-4 text-sm">
          <span className="text-destructive">{itemsError}</span>
          <Button type="button" variant="outline" size="sm" onClick={() => void reloadItems()}>
            Try again
          </Button>
        </div>
      ) : null}

      <KpiStrip kpis={kpis} loading={loading} />

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1.55fr)_minmax(0,1fr)]">
        <Panel title="Restock next" meta={queue.length ? "Most urgent first" : undefined}>
          {loading ? (
            <div className="flex flex-col gap-3 px-5 pt-2 pb-5">
              {Array.from({ length: 4 }, (_, index) => (
                <Skeleton key={index} className="h-12 w-full" />
              ))}
            </div>
          ) : (
            <RestockList queue={queue} onReceive={setReceiving} />
          )}
        </Panel>

        <div className="flex flex-col gap-6">
          <Panel
            title="Recent activity"
            meta={
              <Link to="/activity" className={TEXT_LINK_CLASS}>
                See all
              </Link>
            }
          >
            <RecentActivity />
          </Panel>
          <Link
            to="/insights"
            className="group flex items-center gap-4 rounded-3xl border border-border bg-card px-5 py-4 outline-none transition-colors hover:bg-muted/50 focus-visible:ring-[3px] focus-visible:ring-ring/50"
          >
            <span className="flex size-10 shrink-0 items-center justify-center rounded-2xl bg-primary/12 text-foreground">
              <ChartLineUpIcon className="size-5" />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block text-sm font-semibold">See full analysis</span>
              <span className="block text-xs text-muted-foreground">Stock health, risk by category and reorder amounts</span>
            </span>
            <ArrowRightIcon className="size-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
          </Link>
        </div>
      </div>

      <ReceiveDialog item={receiving} onClose={() => setReceiving(null)} />
      <ItemSheetHost />
    </div>
  );
}
