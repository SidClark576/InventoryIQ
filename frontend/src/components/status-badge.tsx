import { Badge } from "@/components/ui/badge";
import type { StockLevel } from "@/lib/dashboardStats";
import { cn } from "@/lib/utils";

export const LEVEL_LABEL: Record<StockLevel, string> = {
  ok: "In stock",
  low: "Low",
  out: "Out",
};

// Light mode keeps the card behind the text (tinted fills drop it under 4.5:1); dark mode can afford a tint.
const LEVEL_CLASS: Record<StockLevel, string> = {
  ok: "bg-transparent text-success ring-1 ring-success/35 ring-inset dark:bg-success/15 dark:ring-0",
  low: "bg-transparent text-warning ring-1 ring-warning/40 ring-inset dark:bg-warning/15 dark:ring-0",
  out: "bg-transparent text-destructive ring-1 ring-destructive/35 ring-inset dark:bg-destructive/20 dark:ring-0",
};

export const LEVEL_FILL: Record<StockLevel, string> = {
  ok: "bg-success",
  low: "bg-warning",
  out: "bg-destructive",
};

export function StatusBadge({ level, className }: { level: StockLevel; className?: string }) {
  return (
    <Badge variant="secondary" className={cn("gap-1.5 font-semibold", LEVEL_CLASS[level], className)}>
      <span aria-hidden className={cn("size-1.5 rounded-full", LEVEL_FILL[level])} />
      {LEVEL_LABEL[level]}
    </Badge>
  );
}
