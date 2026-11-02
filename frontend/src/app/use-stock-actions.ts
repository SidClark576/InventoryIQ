import { useCallback } from "react";
import { toast } from "sonner";
import {
  addItem,
  ApiError,
  deleteItem,
  itemFromResponse,
  restoreItem,
  updateItem,
  type InventoryItem,
} from "@/api";
import { useInventory } from "@/app/inventory-store";
import { quantityOf } from "@/lib/dashboardStats";
import { errorText } from "@/lib/errors";
import { reasonNote, type Reason } from "@/lib/reasons";

export type ItemFields = {
  name?: string;
  category?: string;
  price?: number;
  lowStockThreshold?: number;
  description?: string;
  barcode?: string;
  /** `YYYY-MM-DD`; "" clears it. */
  expiresAt?: string;
};

type QuantityOptions = {
  /** Offer an Undo button that puts the previous quantity back. Default true. */
  undoable?: boolean;
  /** Suppress toasts (bulk flows show one summary instead). Failures return null. */
  silent?: boolean;
};


/** Undo toasts stay longer than Sonner's 4s default so there is time to react; bulk ones longer still. */
const UNDO_TOAST_MS = 10_000;
const BULK_UNDO_TOAST_MS = 15_000;

/** Someone else got there first: 410 on delete, 409 on restore. Not an error, just stale data. */
function isGone(result: PromiseSettledResult<unknown> | undefined, status: number): boolean {
  return result?.status === "rejected" && result.reason instanceof ApiError && result.reason.status === status;
}

function nameOf(item: InventoryItem): string {
  return item.name || "Item";
}

/** Items saved before versioning have no `version`; the server compares against 0 then. */
function versionOf(item: InventoryItem): number {
  const version = Number(item.version);
  return Number.isFinite(version) ? version : 0;
}

/**
 * Writes through `api.ts` and keeps the shared item cache in step:
 * every successful PUT replaces the cached row with `response.item` (new version),
 * and a 412 reloads the list so the next attempt uses the current version.
 */
export function useStockActions() {
  const { upsertItem, removeItems, reloadItems, invalidateTransactions, quantityQueue, serverItem, stageQuantity } =
    useInventory();

  const reportFailure = useCallback(
    (err: unknown, item: InventoryItem, fallback: string) => {
      if (err instanceof ApiError && err.status === 412) {
        toast.error(`${nameOf(item)} was changed by someone else`, {
          description: "Loaded the latest stock. Check the numbers and try again.",
        });
        void reloadItems();
        return;
      }
      toast.error(fallback, { description: errorText(err, "Try again in a moment.") });
    },
    [reloadItems],
  );

  const putItem = useCallback(
    async (item: InventoryItem, body: Record<string, unknown>): Promise<InventoryItem | null> => {
      if (!item.itemID) return null;
      const result = await updateItem(item.itemID, body, versionOf(item));
      const saved = itemFromResponse(result) ?? { ...item, ...body, version: versionOf(item) + 1 };
      upsertItem(saved);
      invalidateTransactions();
      return saved;
    },
    [upsertItem, invalidateTransactions],
  );

  /** "X: 4 → 3" with Undo. Undo drops taps not sent yet, waits for a save in flight, then puts `before` back. */
  const toastSaved = useCallback(
    (item: InventoryItem, before: number, next: number, notes: string, undoable: boolean) => {
      const id = item.itemID;
      const undo = () => {
        if (!id) return;
        // replace keeps the item pending, so the store keeps its server row for the check below.
        void quantityQueue.replace(id, async () => {
          const latest = serverItem(id);
          if (!latest || quantityOf(latest) !== next) {
            toast.error("Can't undo", { description: `${nameOf(item)} has changed since.` });
            return;
          }
          try {
            await putItem(latest, { quantity: before, notes: "Undo" });
            toast.success(`${nameOf(item)} is back to ${before}`);
          } catch (err: unknown) {
            reportFailure(err, latest, "Undo failed");
          }
        });
        const server = serverItem(id);
        if (server) upsertItem(server);
      };
      toast.success(`${nameOf(item)}: ${before} → ${next}`, {
        description: notes || undefined,
        action: undoable ? { label: "Undo", onClick: undo } : undefined,
        duration: undoable ? UNDO_TOAST_MS : undefined,
      });
    },
    [quantityQueue, serverItem, upsertItem, putItem, reportFailure],
  );

  /** Waits for the save (bulk flows). Taps from steppers and the sheet use `setQuantityOptimistic`. */
  const setQuantity = useCallback(
    async (
      item: InventoryItem,
      next: number,
      notes: string,
      { undoable = true, silent = false }: QuantityOptions = {},
    ): Promise<InventoryItem | null> => {
      const before = quantityOf(item);
      if (next === before) return item;
      try {
        const saved = await putItem(item, { quantity: next, notes });
        if (saved && !silent) toastSaved(item, before, next, notes, undoable);
        return saved;
      } catch (err: unknown) {
        if (!silent) reportFailure(err, item, `Couldn't update ${nameOf(item)}`);
        return null;
      }
    },
    [putItem, toastSaved, reportFailure],
  );

  /** One save of `total` units on top of the server row; on failure the cache goes back to that row. */
  const saveBatch = useCallback(
    async (id: string, total: number, reason: Reason | null): Promise<boolean> => {
      const base = serverItem(id);
      if (!base) return false;
      const before = quantityOf(base);
      const next = Math.max(0, before + total);
      if (next === before) return true;
      const notes = reasonNote(reason, next > before ? "add" : "remove", Math.abs(next - before));
      try {
        if (await putItem(base, { quantity: next, notes })) toastSaved(base, before, next, notes, true);
        return true;
      } catch (err: unknown) {
        quantityQueue.cancel(id);
        if (err instanceof ApiError && (err.status === 404 || err.status === 410)) {
          removeItems([id]);
          toast.error(`${nameOf(base)} was deleted`, { description: "Someone removed it, so the change wasn't saved." });
          return false;
        }
        upsertItem(base);
        if (err instanceof ApiError && err.status === 412) reportFailure(err, base, "");
        else toast.error(`Couldn't save ${nameOf(base)}. It's back to ${before}`, { description: errorText(err, "Try again in a moment.") });
        return false;
      }
    },
    [serverItem, putItem, toastSaved, quantityQueue, removeItems, upsertItem, reportFailure],
  );

  /** The cached number moves now; taps on one item with the same reason merge into one save ~1 s later. */
  const setQuantityOptimistic = useCallback(
    (item: InventoryItem, delta: number, reason: Reason | null = null) => {
      const id = item.itemID;
      if (!id || !delta) return;
      stageQuantity(id, delta);
      quantityQueue.tap(id, delta, reason ?? "", (total) => saveBatch(id, total, reason));
    },
    [stageQuantity, quantityQueue, saveBatch],
  );

  const saveFields = useCallback(
    async (item: InventoryItem, fields: ItemFields): Promise<InventoryItem | null> => {
      try {
        const saved = await putItem(item, fields);
        toast.success(`Saved ${saved?.name || nameOf(item)}`);
        return saved;
      } catch (err: unknown) {
        reportFailure(err, item, `Couldn't save ${nameOf(item)}`);
        return null;
      }
    },
    [putItem, reportFailure],
  );

  const createItem = useCallback(
    async (fields: ItemFields & { quantity: number }, idemKey: string): Promise<InventoryItem | null> => {
      try {
        const result = await addItem(fields, idemKey);
        const created = itemFromResponse(result);
        if (created) upsertItem(created);
        else void reloadItems();
        invalidateTransactions();
        toast.success(`Added ${fields.name || "item"}`);
        return created;
      } catch (err: unknown) {
        toast.error("Couldn't add the item", { description: errorText(err, "Try again.") });
        return null;
      }
    },
    [upsertItem, reloadItems, invalidateTransactions],
  );

  const restoreItems = useCallback(
    async (targets: readonly InventoryItem[]): Promise<string[]> => {
      const results = await Promise.allSettled(
        targets.map((item) => (item.itemID ? restoreItem(item.itemID) : Promise.reject(new Error("No id")))),
      );
      const restored = targets.filter((_, index) => results[index]?.status === "fulfilled");
      const already = results.filter((result) => isGone(result, 409)).length;
      const failed = targets.length - restored.length - already;
      if (already) toast("Already restored");
      if (restored.length || already) {
        await reloadItems();
        invalidateTransactions();
      }
      if (failed) toast.error(`Couldn't restore ${failed} item${failed === 1 ? "" : "s"}`);
      return restored.flatMap((item) => (item.itemID ? [item.itemID] : []));
    },
    [reloadItems, invalidateTransactions],
  );

  /** Soft-deletes; the toast offers Undo, which restores (the backend keeps items 30 days). */
  const deleteItems = useCallback(
    async (targets: readonly InventoryItem[]): Promise<string[]> => {
      const results = await Promise.allSettled(
        targets.map((item) => (item.itemID ? deleteItem(item.itemID) : Promise.reject(new Error("No id")))),
      );
      const deleted = targets.filter((_, index) => results[index]?.status === "fulfilled");
      const already = results.filter((result) => isGone(result, 410)).length;
      const failed = targets.length - deleted.length - already;
      const ids = deleted.flatMap((item) => (item.itemID ? [item.itemID] : []));
      removeItems(ids);
      invalidateTransactions();
      if (already) {
        toast("Already deleted");
        await reloadItems();
      }
      if (deleted.length) {
        const label = deleted.length === 1 ? `Deleted ${nameOf(deleted[0]!)}` : `Deleted ${deleted.length} items`;
        toast.success(label, {
          description: "Restore from Show deleted for 30 days.",
          duration: deleted.length === 1 ? UNDO_TOAST_MS : BULK_UNDO_TOAST_MS,
          action: {
            label: "Undo",
            onClick: () => {
              void restoreItems(deleted).then((restored) => {
                if (restored.length) toast.success(`Restored ${restored.length === 1 ? nameOf(deleted[0]!) : `${restored.length} items`}`);
              });
            },
          },
        });
      }
      if (failed) {
        const first = results.find((result) => result.status === "rejected" && !isGone(result, 410));
        toast.error(`Couldn't delete ${failed} item${failed === 1 ? "" : "s"}`, {
          description: first && first.status === "rejected" ? errorText(first.reason, "") : undefined,
        });
      }
      return ids;
    },
    [removeItems, invalidateTransactions, restoreItems, reloadItems],
  );

  return { setQuantity, setQuantityOptimistic, saveFields, createItem, deleteItems, restoreItems, reportFailure };
}
