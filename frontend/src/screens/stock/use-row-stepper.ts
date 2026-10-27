import { useEffect, useRef, useState } from "react";
import type { InventoryItem } from "@/api";
import { useInventory } from "@/app/inventory-store";
import { useStockActions } from "@/app/use-stock-actions";
import { quantityOf } from "@/lib/dashboardStats";
import { clampDelta, serialize, settleStep } from "./stepper";

const BATCH_MS = 600;

type Batch = { delta: number; timer?: ReturnType<typeof setTimeout> };

/**
 * Row −/+ taps: the row moves at once (`pending` overlay), and taps within 600ms of each other
 * become one write ("Sold 3") through setQuantity (If-Match, 412 reload, Undo toast).
 * Writes for the same item run one after another, each from the item the previous write saved.
 */
export function useRowStepper() {
  const { setQuantity } = useStockActions();
  const { getItem } = useInventory();
  const [pending, setPending] = useState<ReadonlyMap<string, number>>(new Map());
  const batches = useRef(new Map<string, Batch>());
  const writes = useRef(new Map<string, Promise<InventoryItem | null>>());

  function shift(id: string, by: number) {
    setPending((prev) => {
      const next = new Map(prev);
      const total = (next.get(id) ?? 0) + by;
      if (total) next.set(id, total);
      else next.delete(id);
      return next;
    });
  }

  function flush(id: string) {
    const batch = batches.current.get(id);
    if (!batch) return;
    clearTimeout(batch.timer);
    batches.current.delete(id);
    void serialize(writes.current, id, async (saved) => {
      const item = saved ?? getItem(id);
      const settled = item ? settleStep(quantityOf(item), batch.delta) : null;
      const result = item && settled ? await setQuantity(item, settled.next, settled.notes) : null;
      shift(id, -batch.delta);
      return result;
    });
  }

  // Leaving the screen mid-batch still saves the taps (flush only touches refs and stable store callbacks).
  useEffect(() => () => [...batches.current.keys()].forEach(flush), []);

  function step(item: InventoryItem, by: 1 | -1) {
    const id = item.itemID;
    if (!id) return;
    const delta = clampDelta(quantityOf(item) + (pending.get(id) ?? 0), by);
    if (!delta) return;
    const batch = batches.current.get(id) ?? { delta: 0 };
    clearTimeout(batch.timer);
    batch.delta += delta;
    batch.timer = setTimeout(() => flush(id), BATCH_MS);
    batches.current.set(id, batch);
    shift(id, delta);
  }

  return { pending, step };
}
