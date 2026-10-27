import { cn } from "@/lib/utils";

// Logo B "Stocked": a P of 9 rounded boxes on a 3x4 grid (docs/brand/b-symbol.svg).
const CELLS = [
  [48, 20], [104, 20], [160, 20],
  [48, 76], [160, 76],
  [48, 132], [104, 132], [160, 132],
  [48, 188],
] as const;

export function BrandMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 256 256" aria-hidden className={cn("size-7 shrink-0 fill-primary", className)}>
      {CELLS.map(([x, y]) => (
        <rect key={`${x}-${y}`} x={x} y={y} width="48" height="48" rx="8" />
      ))}
    </svg>
  );
}
