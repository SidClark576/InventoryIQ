import { cn } from "@/lib/utils";

type StockBarProps = {
  inStock: number;
  low: number;
  out: number;
  className?: string;
};

const SEGMENTS = [
  { key: "inStock", label: "In stock", fill: "bg-success" },
  { key: "low", label: "Low", fill: "bg-warning" },
  { key: "out", label: "Out", fill: "bg-destructive" },
] as const;

function count(value: number): number {
  return Number.isFinite(value) ? Math.max(0, value) : 0;
}

export function StockBar({ inStock, low, out, className }: StockBarProps) {
  const counts = { inStock: count(inStock), low: count(low), out: count(out) };

  return (
    <div className={cn("flex flex-col gap-3", className)}>
      <div aria-hidden="true" className="flex h-3 w-full gap-0.5 overflow-hidden rounded-full bg-muted">
        {SEGMENTS.map((seg) =>
          counts[seg.key] > 0 ? (
            <div key={seg.key} className={cn("h-full basis-0", seg.fill)} style={{ flexGrow: counts[seg.key] }} />
          ) : null,
        )}
      </div>
      <ul aria-label="Stock distribution" className="flex flex-wrap gap-x-5 gap-y-2 text-xs font-medium">
        {SEGMENTS.map((seg) => (
          <li key={seg.key} className="flex items-center gap-2 text-muted-foreground">
            <span aria-hidden="true" className={cn("size-2 rounded-full", seg.fill)} />
            {seg.label}
            <span className="text-foreground tabular-nums">{counts[seg.key]}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
