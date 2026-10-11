import type { ReactNode } from "react";
import { deltaOf, isWasteNote, quantityAfterOf, type Transaction } from "@/lib/activity";
import { cn } from "@/lib/utils";

const TYPE_LABEL: Record<string, string> = {
  create: "New",
  delete: "Deleted",
  update: "Edit",
};

export function DeltaChip({ tx }: { tx: Transaction }) {
  const type = tx.changeType ?? "";
  const delta = deltaOf(tx);
  const base = "inline-flex h-6 min-w-12 shrink-0 items-center justify-center rounded-full px-2 text-xs font-semibold tabular-nums";
  if (type === "stock_in" || (type !== "stock_out" && delta > 0 && !TYPE_LABEL[type])) {
    return (
      <span className={cn(base, "text-success ring-1 ring-success/35 ring-inset dark:bg-success/15 dark:ring-0")}>
        +{Math.abs(delta)}
      </span>
    );
  }
  if (type === "stock_out") {
    const waste = isWasteNote(tx.notes);
    return (
      <span className={cn(base, waste
            ? "text-destructive ring-1 ring-destructive/35 ring-inset dark:bg-destructive/20 dark:ring-0"
            : "bg-muted text-foreground")}>
        −{Math.abs(delta)}
      </span>
    );
  }
  return (
    <span className={cn(base, "border border-border text-muted-foreground")}>{TYPE_LABEL[type] ?? "Edit"}</span>
  );
}

type ActivityRowProps = {
  tx: Transaction;
  /** Item name, rendered as a link when the item still exists. */
  name: ReactNode;
  time: string;
  className?: string;
};

export function ActivityRow({ tx, name, time, className }: ActivityRowProps) {
  const after = quantityAfterOf(tx);
  const moved = tx.changeType === "stock_in" || tx.changeType === "stock_out";
  return (
    <li className={cn("flex items-center gap-3 py-2.5", className)}>
      <DeltaChip tx={tx} />
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-medium">{name}</div>
        {tx.notes ? <div className="truncate text-xs text-muted-foreground">{tx.notes}</div> : null}
      </div>
      <div className="shrink-0 text-right text-xs text-muted-foreground tabular-nums">
        {moved && after !== null ? <div className="text-foreground">now {after}</div> : null}
        <div>{time}</div>
      </div>
    </li>
  );
}
