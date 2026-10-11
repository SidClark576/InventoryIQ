import { Link } from "react-router";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

export type Kpi = {
  id: string;
  label: string;
  value: string;
  to: string;
  tone?: "warning" | "destructive";
};

const TONE: Record<NonNullable<Kpi["tone"]>, string> = {
  warning: "text-warning",
  destructive: "text-destructive",
};

export function KpiStrip({ kpis, loading }: { kpis: readonly Kpi[]; loading: boolean }) {
  return (
    <ul className="grid grid-cols-2 overflow-hidden rounded-3xl border border-border bg-card sm:grid-cols-4">
      {kpis.map((kpi, index) => (
        <li
          key={kpi.id}
          className={cn(
            "border-border",
            index % 2 === 1 && "border-l",
            index >= 2 && "border-t sm:border-t-0",
            index === 2 && "sm:border-l",
          )}
        >
          <Link
            to={kpi.to}
            className="flex h-full flex-col gap-1 px-5 py-4 outline-none transition-colors hover:bg-muted/50 focus-visible:bg-muted/60 focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:ring-inset"
          >
            <span className="text-xs font-medium text-muted-foreground">{kpi.label}</span>
            <span id={kpi.id}>
              {loading ? (
                <Skeleton className="h-8 w-16" />
              ) : (
                <span
                  className={cn(
                    "font-heading text-3xl font-semibold tracking-tight tabular-nums",
                    kpi.tone && kpi.value !== "0" ? TONE[kpi.tone] : undefined,
                  )}
                >
                  {kpi.value}
                </span>
              )}
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}
