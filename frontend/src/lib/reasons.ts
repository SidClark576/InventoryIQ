/**
 * Stock change reasons. The backend has no reason field: the reason travels in the
 * free-text `notes` of PUT /items/{id}, and the server derives stock_in / stock_out
 * from the quantity difference.
 */
export const REASONS = ["Used", "Waste", "Damaged", "Received", "Count fix"] as const;

export type Reason = (typeof REASONS)[number];

export type Direction = "add" | "remove";

const REMOVE_ONLY: readonly Reason[] = ["Used", "Waste", "Damaged"];

export function reasonAllows(reason: Reason | null, direction: Direction): boolean {
  if (!reason || reason === "Count fix") return true;
  if (reason === "Received") return direction === "add";
  return direction === "remove" && REMOVE_ONLY.includes(reason);
}

/** Note text for a change of `amount` units. Without a reason, removals are "Used" and additions "Received". */
export function reasonNote(reason: Reason | null, direction: Direction, amount: number): string {
  const effective: Reason = reason ?? (direction === "add" ? "Received" : "Used");
  if (effective === "Count fix") return "Count fix";
  if (effective === "Waste" || effective === "Damaged") return `${effective}: ${amount}`;
  return `${effective} ${amount}`;
}

/** Quantity after applying `amount` in `direction`, never below zero. */
export function nextQuantity(current: number, direction: Direction, amount: number): number {
  const next = direction === "add" ? current + amount : current - amount;
  return Math.max(0, next);
}
