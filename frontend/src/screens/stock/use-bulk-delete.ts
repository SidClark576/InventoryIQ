import { useRef, useState } from "react";
import type { InventoryItem } from "@/api";
import { useStockActions } from "@/app/use-stock-actions";
import { bulkDeleteNeedsConfirm } from "./stock-view";

/** Under 10 rows deletes at once (Undo in the toast); 10+ rows or every shown row asks first. */
export function useBulkDelete(selectedItems: readonly InventoryItem[], shownCount: number, setSelected: (ids: ReadonlySet<string>) => void) {
  const { deleteItems } = useStockActions();
  const [confirming, setConfirming] = useState(false);
  // A double tap on Delete must not send the same rows twice (the second would toast "Already deleted").
  const running = useRef(false);

  async function run() {
    setConfirming(false);
    if (running.current) return;
    running.current = true;
    let deleted: Set<string>;
    try {
      deleted = new Set(await deleteItems(selectedItems));
    } finally {
      running.current = false;
    }
    // Rows that failed stay selected so a retry is one click.
    setSelected(new Set(selectedItems.flatMap((item) => (item.itemID && !deleted.has(item.itemID) ? [item.itemID] : []))));
  }

  function ask() {
    if (bulkDeleteNeedsConfirm(selectedItems.length, shownCount)) setConfirming(true);
    else void run();
  }

  return { confirming, setConfirming, ask, run };
}
