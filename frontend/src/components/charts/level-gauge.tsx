import { LEVEL_FILL } from "@/components/status-badge";
import type { StockLevel } from "@/lib/dashboardStats";
import { cn } from "@/lib/utils";

type LevelGaugeProps = {
  quantity: number;
  threshold: number;
  level: StockLevel;
  className?: string;
};

/**
 * Horizontal fill of quantity against a scale of 3x the low-stock alert,
 * with a tick at the alert level so "how close to reorder" reads at a glance.
 */
export function LevelGauge({ quantity, threshold, level, className }: LevelGaugeProps) {
  const max = Math.max(threshold * 3, quantity, 1);
  const fill = Math.min(100, (Math.max(quantity, 0) / max) * 100);
  const tick = Math.min(100, (threshold / max) * 100);
  return (
    <div
      role="img"
      aria-label={`${quantity} on hand, alert at ${threshold}`}
      className={cn("relative h-1.5 w-full min-w-16 rounded-full bg-muted", className)}
    >
      <div
        className={cn("h-full rounded-full", LEVEL_FILL[level])}
        style={{ width: `${fill}%` }}
      />
      <div
        aria-hidden
        className="absolute -top-1 h-3.5 w-0.5 rounded-full bg-foreground/45"
        style={{ left: `calc(${tick}% - 1px)` }}
      />
    </div>
  );
}
