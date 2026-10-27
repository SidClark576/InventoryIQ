import type { ReactNode } from "react";
import { LEVEL_FILL } from "@/components/status-badge";
import type { StockLevel } from "@/lib/dashboardStats";
import { formatMoney } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { StatusFilter } from "./stock-view";

const SEGMENTS: readonly { level: StockLevel; label: string }[] = [
  { level: "out", label: "Out" },
  { level: "low", label: "Low" },
  { level: "ok", label: "In stock" },
];

type HealthBarProps = {
  counts: Record<StockLevel, number>;
  total: number;
  value: number;
  status: StatusFilter;
  onStatus: (status: StatusFilter) => void;
};

function LegendButton({
  pressed,
  onClick,
  children,
}: {
  pressed: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      onClick={onClick}
      className={cn(
        "inline-flex h-8 touch:min-h-11 items-center gap-1.5 rounded-full border px-2.5 text-sm sm:gap-2 sm:px-3 transition-colors outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50",
        pressed
          ? "border-foreground/80 bg-foreground text-background"
          : "border-transparent text-muted-foreground hover:bg-muted hover:text-foreground",
      )}
    >
      {children}
    </button>
  );
}

/** Stock health at a glance; the legend doubles as the status filter. */
export function HealthBar({ counts, total, value, status, onStatus }: HealthBarProps) {
  return (
    <section aria-label="Stock health" className="flex flex-col gap-3">
      <div aria-hidden className="flex h-2.5 w-full gap-1 overflow-hidden rounded-full bg-muted">
        {SEGMENTS.map((segment) =>
          counts[segment.level] > 0 ? (
            <div
              key={segment.level}
              className={cn(
                "h-full rounded-full transition-opacity",
                LEVEL_FILL[segment.level],
                status !== "all" && status !== segment.level && "opacity-25",
              )}
              style={{ flexGrow: counts[segment.level], flexBasis: 0 }}
            />
          ) : null,
        )}
      </div>
      <div className="flex flex-wrap items-center gap-x-1 gap-y-2">
        <div role="group" aria-label="Filter by status" className="flex flex-wrap items-center gap-0.5 sm:gap-1">
          <LegendButton pressed={status === "all"} onClick={() => onStatus("all")}>
            All <b className="font-semibold tabular-nums">{total}</b>
          </LegendButton>
          {SEGMENTS.map((segment) => (
            <LegendButton
              key={segment.level}
              pressed={status === segment.level}
              onClick={() => onStatus(status === segment.level ? "all" : segment.level)}
            >
              <span aria-hidden className={cn("size-2 rounded-full", LEVEL_FILL[segment.level])} />
              {segment.label} <b className="font-semibold tabular-nums">{counts[segment.level]}</b>
            </LegendButton>
          ))}
        </div>
        <span className="ml-auto text-sm text-muted-foreground tabular-nums">{formatMoney(value)} on hand</span>
      </div>
    </section>
  );
}
