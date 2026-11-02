import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router";
import { ArrowClockwiseIcon } from "@phosphor-icons/react";
import { ensureOrgContext, getTransactions, type InventoryItem } from "@/api";
import { useOrgShell } from "@/app/AppLayout";
import { useInventory, type LoadStatus } from "@/app/inventory-store";
import { SHEET_LINK_STATE, useSheetParams } from "@/app/use-sheet-params";
import { PageHeader } from "@/components/page-header";
import { RadialGauge } from "@/components/charts/radial-gauge";
import { StockBar } from "@/components/charts/stock-bar";
import { TEXT_LINK_CLASS } from "@/components/text-link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { parseTransactions, type Transaction } from "@/lib/activity";
import { quantityOf } from "@/lib/dashboardStats";
import { errorText } from "@/lib/errors";
import { formatCompactMoney } from "@/lib/format";
import { deriveInsights, HISTORY_DAYS, RUNS_OUT_WITHIN_DAYS } from "@/lib/insights";
import { cn } from "@/lib/utils";
import { getCurrentOrg } from "@/session";

/** Long lists show this many rows, then "See all". */
const TOP = 8;

type History = { status: LoadStatus; rows: Transaction[]; error: string };
type CardState = { status: LoadStatus; error: string; onRetry: () => void };

// Full class names so Tailwind sees them.
const RISK_TONE = [
  { text: "text-destructive", bar: "bg-destructive" },
  { text: "text-warning", bar: "bg-warning" },
  { text: "text-success", bar: "bg-success" },
] as const;

const days = (n: number) => `${n} day${n === 1 ? "" : "s"}`;

/**
 * Computed in the browser from the shared item cache and the last 30 days of GET /transactions.
 * Never calls GET /insights: that endpoint sends SNS/SQS messages on every request.
 */
export function InsightsScreen() {
  const { orgEpoch } = useOrgShell();
  const { items, itemsStatus, itemsError, reloadItems } = useInventory();
  const [history, setHistory] = useState<History>({ status: "loading", rows: [], error: "" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    document.title = "Insights | Panindo";
  }, []);

  // Only orgEpoch and Retry/Refresh load; never `orgs`. The cleanup drops a response that lands after an org switch.
  useEffect(() => {
    let cancelled = false;
    setHistory({ status: "loading", rows: [], error: "" });
    void (async () => {
      try {
        await ensureOrgContext();
      } catch {
        // Legacy (no-org) mode.
      }
      const orgID = getCurrentOrg();
      const since = new Date(Date.now() - HISTORY_DAYS * 86_400_000).toISOString();
      try {
        const rows = parseTransactions(await getTransactions(since));
        if (!cancelled && getCurrentOrg() === orgID) setHistory({ status: "ready", rows, error: "" });
      } catch (err: unknown) {
        if (cancelled || getCurrentOrg() !== orgID) return;
        setHistory({ status: "error", rows: [], error: errorText(err, "Couldn't load stock history.") });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [orgEpoch, attempt]);

  const insights = useMemo(() => deriveInsights(items, history.rows), [items, history.rows]);
  const retryHistory = () => setAttempt((n) => n + 1);
  const itemsCard: CardState = {
    status: itemsStatus === "idle" ? "loading" : itemsStatus,
    error: itemsError ?? "",
    onRetry: () => void reloadItems(),
  };
  // Cards that also need history wait for (or report) the item cache first.
  const historyCard: CardState = itemsCard.status === "ready" ? { ...history, onRetry: retryHistory } : itemsCard;
  const { stats, health } = insights;

  return (
    <div id="insights-content" className="flex flex-col gap-6">
      <PageHeader
        title="Insights"
        description={`Stock health and trends from the last ${HISTORY_DAYS} days.`}
        actions={
          <Button
            type="button"
            variant="outline"
            disabled={history.status === "loading" || itemsCard.status === "loading"}
            onClick={() => {
              void reloadItems();
              retryHistory();
            }}
          >
            <ArrowClockwiseIcon />
            Refresh
          </Button>
        }
      />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <InsightCard title="Inventory health" state={itemsCard}>
          {health === null ? (
            <p className="text-sm text-muted-foreground">
              Add items to see your stock health.{" "}
              <Link to="/stock?new=1" className={TEXT_LINK_CLASS}>
                Add an item
              </Link>
            </p>
          ) : (
            <div className="flex flex-col items-center text-center">
              <RadialGauge value={health} size={168} label="Health" />
              <p className="mt-4 text-sm text-muted-foreground">
                <span className="font-medium text-foreground tabular-nums">
                  {stats.outOfStockCount + stats.lowStockCount}
                </span>{" "}
                of <span className="tabular-nums">{stats.totalProducts}</span> low or out
              </p>
            </div>
          )}
        </InsightCard>
        <InsightCard title="Stock distribution" state={itemsCard} className="lg:col-span-2">
          <div className="flex flex-col gap-4">
            {stats.totalProducts > 0 ? (
              <StockBar
                inStock={stats.totalProducts - stats.lowStockCount - stats.outOfStockCount}
                low={stats.lowStockCount}
                out={stats.outOfStockCount}
              />
            ) : (
              <p className="text-sm text-muted-foreground">Add items to see your stock mix.</p>
            )}
            <div className="grid grid-cols-2 gap-4">
              <Stat label="Products" value={String(stats.totalProducts)} />
              <Stat label="Inventory value" value={formatCompactMoney(stats.estimatedInventoryValue)} />
            </div>
          </div>
        </InsightCard>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <InsightCard title="Runs out soon" state={historyCard}>
          {insights.estimated === 0 ? (
            <p className="text-sm text-muted-foreground">
              Not enough history yet. An estimate needs 2 or more uses of an item across 3 days.
            </p>
          ) : (
            <ItemList
              empty={`Nothing runs out in the next ${RUNS_OUT_WITHIN_DAYS} days.`}
              rows={insights.runningOut.map(({ item, daysLeft }) => ({ item, detail: `~${days(daysLeft)} left` }))}
            />
          )}
        </InsightCard>
        <InsightCard title="Expiring soon" state={itemsCard}>
          <ItemList
            empty="Nothing expires in the next 7 days."
            rows={insights.expiring.map(({ item, days: left }) => ({
              item,
              detail: left < 0 ? "Expired" : left === 0 ? "Today" : `In ${days(left)}`,
              tone: left < 0 ? "font-medium text-destructive" : undefined,
            }))}
          />
        </InsightCard>
        <InsightCard title="Not moving" state={historyCard}>
          <ItemList
            empty={`Every item in stock moved in the last ${HISTORY_DAYS} days.`}
            rows={insights.notMoving.map((item) => ({ item, detail: `${quantityOf(item)} on hand` }))}
          />
        </InsightCard>
        <InsightCard title="Waste and damage" state={historyCard}>
          {insights.waste.changes === 0 ? (
            <p className="text-sm text-muted-foreground">No waste or damage logged in the last {HISTORY_DAYS} days.</p>
          ) : (
            <div className="grid grid-cols-2 gap-4">
              <Stat label="Units" value={String(insights.waste.units)} />
              <Stat label="Value" value={formatCompactMoney(insights.waste.value)} />
            </div>
          )}
        </InsightCard>
        <InsightCard title="Category risk" state={itemsCard} className="lg:col-span-2">
          {insights.categoryRisk.length === 0 ? (
            <p className="text-sm text-muted-foreground">No categories yet.</p>
          ) : (
            insights.categoryRisk.map((risk) => {
              const tone = RISK_TONE[risk.percent >= 50 ? 0 : risk.percent >= 20 ? 1 : 2];
              return (
                <div key={risk.category} className="border-b border-border py-2.5 last:border-0">
                  <div className="mb-1.5 flex flex-wrap items-center justify-between gap-x-3 text-sm">
                    <span className="font-medium">{risk.category}</span>
                    <span className="text-muted-foreground tabular-nums">
                      <span className={`font-medium ${tone.text}`}>{risk.atRisk}</span>/{risk.total} low or out ·{" "}
                      {risk.percent}%
                    </span>
                  </div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-muted">
                    <div className={`h-full rounded-full ${tone.bar}`} style={{ width: `${risk.percent}%` }} />
                  </div>
                </div>
              );
            })
          )}
        </InsightCard>
      </div>
    </div>
  );
}

function InsightCard({
  title,
  state,
  className,
  children,
}: {
  title: string;
  state: CardState;
  className?: string;
  children: ReactNode;
}) {
  return (
    <Card className={className} aria-busy={state.status === "loading"}>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>
        {state.status === "loading" ? (
          <div className="flex flex-col gap-3" role="status" aria-label={`Loading ${title.toLowerCase()}`}>
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-5/6" />
          </div>
        ) : state.status === "error" ? (
          <div className="flex flex-col items-start gap-3" role="alert">
            <p className="text-sm text-muted-foreground">{state.error || "Couldn't load this right now."}</p>
            <Button type="button" variant="outline" size="sm" onClick={state.onRetry}>
              <ArrowClockwiseIcon />
              Retry
            </Button>
          </div>
        ) : (
          children
        )}
      </CardContent>
    </Card>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-border p-4">
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
    </div>
  );
}

type Row = { item: InventoryItem; detail: string; tone?: string };

/** Item names open the item sheet (read-only for viewers); long lists show TOP rows, then "See all". */
function ItemList({ rows, empty }: { rows: Row[]; empty: string }) {
  const { itemHref } = useSheetParams();
  const [all, setAll] = useState(false);
  if (rows.length === 0) return <p className="text-sm text-muted-foreground">{empty}</p>;
  const shown = all ? rows : rows.slice(0, TOP);
  return (
    <div className="flex flex-col items-start">
      <ul className="w-full">
        {shown.map(({ item, detail, tone }) => (
          <li
            key={item.itemID ?? item.name}
            className="flex min-h-11 items-center justify-between gap-3 border-b border-border text-sm last:border-0"
          >
            {item.itemID ? (
              <Link
                to={itemHref(item.itemID)}
                state={SHEET_LINK_STATE}
                className={cn(TEXT_LINK_CLASS, "min-w-0 truncate py-2 no-underline hover:underline")}
              >
                {item.name || "Unnamed item"}
              </Link>
            ) : (
              <span className="min-w-0 truncate">{item.name || "Unnamed item"}</span>
            )}
            <span className={cn("shrink-0 tabular-nums", tone ?? "text-muted-foreground")}>{detail}</span>
          </li>
        ))}
      </ul>
      {rows.length > TOP ? (
        <Button type="button" variant="link" className="mt-1 px-0" onClick={() => setAll((open) => !open)}>
          {all ? "Show fewer" : `See all ${rows.length}`}
        </Button>
      ) : null}
    </div>
  );
}
