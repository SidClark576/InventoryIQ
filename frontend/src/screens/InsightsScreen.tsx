import { useEffect, useState } from "react";
import { ArrowClockwiseIcon } from "@phosphor-icons/react";
import { ensureOrgContext, getInsights } from "@/api";
import { useOrgShell } from "@/app/AppLayout";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { RadialGauge } from "@/components/charts/radial-gauge";
import { StockBar } from "@/components/charts/stock-bar";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { getCurrentOrg } from "@/session";
import { errorText } from "@/lib/errors";
import { formatCompactMoney } from "@/lib/format";

type StockItem = { name?: unknown; quantity?: unknown };
type ReorderItem = {
  urgency?: string;
  name?: unknown;
  category?: unknown;
  currentQuantity?: string | number | null;
  suggestedOrderQuantity?: string | number | null;
};
type RiskItem = {
  riskPercent?: unknown;
  category?: unknown;
  atRiskItems?: string | number | null;
  totalItems?: string | number | null;
};

type InsightView = {
  healthScore: number;
  atRiskCount: number;
  totalProducts: number;
  estValue: number;
  lowCount: number;
  outCount: number;
  inStockCount: number;
  recommendations: unknown[];
  reorder: ReorderItem[];
  risks: RiskItem[];
  lowItems: StockItem[];
  outItems: StockItem[];
};

const URGENCY: Record<string, { className: string; bar: string; label: string }> = {
  critical: { className: "text-destructive", bar: "bg-destructive", label: "Critical" },
  high: { className: "text-warning", bar: "bg-warning", label: "High" },
  medium: { className: "text-muted-foreground", bar: "bg-muted-foreground", label: "Medium" },
  low: { className: "text-success", bar: "bg-success", label: "Low" },
};

function finite(value: unknown, fallback: number): number {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function text(value: unknown): string {
  if (value === null || value === undefined || value === false) return "";
  return String(value);
}



function parseInsights(raw: Record<string, unknown>): InsightView {
  const summary = (raw.summary ?? {}) as Record<string, unknown>;
  const lowItems = Array.isArray(raw.lowStockItems) ? (raw.lowStockItems as StockItem[]) : [];
  const outItems = Array.isArray(raw.outOfStockItems) ? (raw.outOfStockItems as StockItem[]) : [];
  const totalProducts = finite(summary.totalProducts, 0);
  const lowCount = finite(summary.lowStockCount, lowItems.length);
  const outCount = finite(summary.outOfStockCount, outItems.length);
  return {
    healthScore: finite(summary.healthScore, 100),
    atRiskCount: finite(summary.atRiskCount, 0),
    totalProducts,
    estValue: finite(summary.estimatedInventoryValue, 0),
    lowCount,
    outCount,
    inStockCount: Math.max(0, totalProducts - lowCount - outCount),
    recommendations: Array.isArray(raw.recommendations) ? raw.recommendations : [],
    reorder: Array.isArray(raw.topReorderPriorities) ? (raw.topReorderPriorities as ReorderItem[]) : [],
    risks: Array.isArray(raw.categoryRiskBreakdown) ? (raw.categoryRiskBreakdown as RiskItem[]) : [],
    lowItems,
    outItems,
  };
}

// GET /insights queues an SQS message and can send an SNS alert on every call.
// Share one in-flight request per org so a StrictMode remount or a quick
// re-render never fires a second one; Refresh starts a new request explicitly.
let inflight: { orgID: string; request: Promise<Record<string, unknown>> } | null = null;

function loadInsightsOnce(orgID: string): Promise<Record<string, unknown>> {
  if (inflight && inflight.orgID === orgID) return inflight.request;
  const request = getInsights().finally(() => {
    if (inflight?.request === request) inflight = null;
  });
  inflight = { orgID, request };
  return request;
}

export function InsightsScreen() {
  const { orgEpoch } = useOrgShell();
  const [view, setView] = useState<InsightView | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);

  useEffect(() => {
    document.title = "Insights | InventoryIQ";
  }, []);

  // Only orgEpoch and an explicit Refresh trigger a load; never `orgs` (it changes right after mount).
  useEffect(() => {
    let cancelled = false;
    setView(null);
    setError(null);
    setLoading(true);
    void (async () => {
      try {
        await ensureOrgContext();
      } catch {
        // Legacy (no-org) mode.
      }
      const orgID = getCurrentOrg();
      if (cancelled) return;
      try {
        const raw = await loadInsightsOnce(orgID);
        if (cancelled || getCurrentOrg() !== orgID) return;
        setView(parseInsights(raw));
      } catch (err: unknown) {
        if (cancelled || getCurrentOrg() !== orgID) return;
        setView(null);
        setError(errorText(err));
      } finally {
        if (!cancelled && getCurrentOrg() === orgID) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [orgEpoch, refreshToken]);

  return (
    <div id="insights-content" className="flex flex-col gap-6">
      <PageHeader
        title="Insights"
        description="Stock health, category risk, and what to reorder next."
        actions={
          <Button
            type="button"
            variant="outline"
            disabled={loading}
            onClick={() => setRefreshToken((token) => token + 1)}
          >
            <ArrowClockwiseIcon />
            Refresh
          </Button>
        }
      />

      {loading ? <InsightsSkeleton /> : null}
      {!loading && error ? (
        <Card>
          <CardContent className="py-10 text-center">
            <p className="font-medium">Unable to analyze right now</p>
            <p className="mt-1 text-sm text-muted-foreground">{error}</p>
          </CardContent>
        </Card>
      ) : null}
      {!loading && !error && view ? <InsightsBody view={view} /> : null}
    </div>
  );
}

function InsightsSkeleton() {
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      <Card className="items-center">
        <CardContent>
          <Skeleton className="size-40 rounded-full" />
        </CardContent>
      </Card>
      <Card className="lg:col-span-2">
        <CardContent className="flex flex-col gap-3">
          <Skeleton className="h-4 w-40" />
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-3/4" />
          <Skeleton className="h-3 w-5/6" />
        </CardContent>
      </Card>
    </div>
  );
}

function InsightsBody({ view }: { view: InsightView }) {
  return (
    <>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card>
          <CardContent className="flex flex-col items-center text-center">
            <RadialGauge value={view.healthScore} size={168} label="Health" />
            <p className="mt-4 text-sm font-medium text-muted-foreground">Inventory health score</p>
            <p className="mt-1 text-sm text-muted-foreground">
              <span className="font-medium text-foreground tabular-nums">{view.atRiskCount}</span> of{" "}
              <span className="tabular-nums">{view.totalProducts}</span> at risk
            </p>
          </CardContent>
        </Card>
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Stock distribution</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <StockBar inStock={view.inStockCount} low={view.lowCount} out={view.outCount} />
            <div className="grid grid-cols-2 gap-4">
              <div className="rounded-xl border border-border p-4">
                <p className="text-sm text-muted-foreground">Products</p>
                <p className="mt-1 text-2xl font-semibold tabular-nums">{view.totalProducts}</p>
              </div>
              <div className="rounded-xl border border-border p-4">
                <p className="text-sm text-muted-foreground">Inventory value</p>
                <p className="mt-1 text-2xl font-semibold tabular-nums">{formatCompactMoney(view.estValue)}</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Recommendations</CardTitle>
          </CardHeader>
          <CardContent>
            {view.recommendations.length === 0 ? (
              <p className="text-sm text-muted-foreground">All clear — no recommendations right now.</p>
            ) : (
              <ul className="flex flex-col gap-2">
                {view.recommendations.map((item, index) => (
                  <li key={index} className="border-b border-border py-2 text-sm text-muted-foreground last:border-0">
                    {text(item)}
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Top reorder priorities</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-2">
            {view.reorder.length === 0 ? (
              <p className="text-sm text-muted-foreground">No reorder priorities yet.</p>
            ) : (
              view.reorder.map((item, index) => {
                const urgency = URGENCY[item.urgency || ""] ?? URGENCY.low;
                return (
                  <div key={index} className="relative overflow-hidden rounded-xl border border-border px-4 py-3 pl-5">
                    <span className={`absolute inset-y-0 left-0 w-1 ${urgency.bar}`} />
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium">{text(item.name)}</p>
                        <p className="text-xs text-muted-foreground">
                          {text(item.category) || "Uncategorized"} · Qty{" "}
                          <span className="tabular-nums">{item.currentQuantity}</span>
                        </p>
                      </div>
                      <div className="shrink-0 text-right">
                        <p className={`text-xs font-medium ${urgency.className}`}>{urgency.label}</p>
                        <p className="text-xs text-muted-foreground">
                          Reorder{" "}
                          <span className="font-medium text-foreground tabular-nums">~{item.suggestedOrderQuantity}</span>
                        </p>
                      </div>
                    </div>
                  </div>
                );
              })
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Category risk</CardTitle>
          </CardHeader>
          <CardContent>
            {view.risks.length === 0 ? (
              <p className="text-sm text-muted-foreground">No category data.</p>
            ) : (
              view.risks.map((risk, index) => {
                const pct = Number(risk.riskPercent) || 0;
                const tone = pct >= 50 ? "bg-destructive" : pct >= 20 ? "bg-warning" : "bg-success";
                const textTone = pct >= 50 ? "text-destructive" : pct >= 20 ? "text-warning" : "text-success";
                return (
                  <div key={index} className="border-b border-border py-2.5 last:border-0">
                    <div className="mb-1.5 flex items-center justify-between text-sm">
                      <span className="font-medium">{text(risk.category)}</span>
                      <span className="text-muted-foreground tabular-nums">
                        <span className={`font-medium ${textTone}`}>{risk.atRiskItems}</span>/{risk.totalItems} · {pct}%
                      </span>
                    </div>
                    <div className="h-1.5 overflow-hidden rounded-full bg-muted">
                      <div className={`h-full rounded-full ${tone}`} style={{ width: `${Math.min(100, pct)}%` }} />
                    </div>
                  </div>
                );
              })
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Stock watch</CardTitle>
          </CardHeader>
          <CardContent>
            <Tabs defaultValue="low">
              <TabsList>
                <TabsTrigger value="low">Low stock</TabsTrigger>
                <TabsTrigger value="out">Out of stock</TabsTrigger>
              </TabsList>
              <TabsContent value="low">
                <StockList
                  empty="No low-stock items."
                  items={view.lowItems.map((item) => ({
                    name: text(item.name),
                    detail: `${String(item.quantity)} left`,
                    detailClass: "font-medium text-foreground tabular-nums",
                  }))}
                />
              </TabsContent>
              <TabsContent value="out">
                <StockList
                  empty="No out-of-stock items."
                  items={view.outItems.map((item) => ({
                    name: text(item.name),
                    detail: "Out",
                    detailClass: "text-xs font-medium text-destructive",
                  }))}
                />
              </TabsContent>
            </Tabs>
          </CardContent>
        </Card>
      </div>
    </>
  );
}

function StockList({
  items,
  empty,
}: {
  items: Array<{ name: string; detail: string; detailClass: string }>;
  empty: string;
}) {
  if (items.length === 0) return <p className="text-sm text-muted-foreground">{empty}</p>;
  return (
    <ul>
      {items.map((item, index) => (
        <li key={index} className="flex items-center justify-between border-b border-border py-2 text-sm last:border-0">
          <span className="text-muted-foreground">{item.name}</span>
          <span className={item.detailClass}>{item.detail}</span>
        </li>
      ))}
    </ul>
  );
}
