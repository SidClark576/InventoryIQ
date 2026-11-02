import type { InventoryItem } from "@/api";
import { useStockActions } from "@/app/use-stock-actions";
import { quantityOf } from "@/lib/dashboardStats";
import { clampDelta } from "./stepper";

/**
 * Row −/+ taps. The cached row moves at once; the store merges taps on the same item (from here, the
 * item sheet or Today) into one save about a second after the last one, and keeps saving after the
 * screen unmounts.
 */
export function useRowStepper() {
  const { setQuantityOptimistic } = useStockActions();

  function step(item: InventoryItem, by: 1 | -1) {
    const delta = clampDelta(quantityOf(item), by);
    if (delta) setQuantityOptimistic(item, delta);
  }

  return { step };
}
