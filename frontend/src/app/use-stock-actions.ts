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
import { getUserEmail } from "@/session";

export type ItemFields = {
  name?: string;
  category?: string;
  price?: number;
  lowStockThreshold?: number;
  description?: string;
  barcode?: string;
};

type QuantityOptions = {
  /** Offer an Undo button that puts the previous quantity back. Default true. */
  undoable?: boolean;
  /** Suppress toasts (bulk flows show one summary instead). Failures return null. */
  silent?: boolean;
};

function errorText(err: unknown, fallback: string): string {
  return err instanceof Error && err.message ? err.message : fallback;
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
  const { getItem, upsertItem, removeItems, reloadItems, invalidateTransactions } = useInventory();

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
      const result = await updateItem(item.itemID, { ...body, userID: getUserEmail() }, versionOf(item));
      const saved = itemFromResponse(result) ?? { ...item, ...body, version: versionOf(item) + 1 };
      upsertItem(saved);
      invalidateTransactions();
      return saved;
    },
    [upsertItem, invalidateTransactions],
  );

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
        if (!saved || silent) return saved;
        const undo = () => {
          const latest = saved.itemID ? getItem(saved.itemID) : undefined;
          if (!latest || quantityOf(latest) !== next) {
            toast.error("Can't undo", { description: `${nameOf(item)} has changed since.` });
            return;
          }
          void (async () => {
            try {
              await putItem(latest, { quantity: before, notes: "Undo" });
              toast.success(`${nameOf(item)} is back to ${before}`);
            } catch (err: unknown) {
              reportFailure(err, latest, "Undo failed");
            }
          })();
        };
        toast.success(`${nameOf(item)}: ${before} → ${next}`, {
          description: notes || undefined,
          action: undoable ? { label: "Undo", onClick: undo } : undefined,
        });
        return saved;
      } catch (err: unknown) {
        if (!silent) reportFailure(err, item, `Couldn't update ${nameOf(item)}`);
        return null;
      }
    },
    [putItem, getItem, reportFailure],
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
    async (fields: ItemFields & { quantity: number }): Promise<InventoryItem | null> => {
      try {
        const result = await addItem({ ...fields, userID: getUserEmail() });
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
      const failed = targets.length - restored.length;
      if (restored.length) {
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
      const failed = targets.length - deleted.length;
      const ids = deleted.flatMap((item) => (item.itemID ? [item.itemID] : []));
      removeItems(ids);
      invalidateTransactions();
      if (deleted.length) {
        const label = deleted.length === 1 ? `Deleted ${nameOf(deleted[0]!)}` : `Deleted ${deleted.length} items`;
        toast.success(label, {
          description: "Restore from Show deleted for 30 days.",
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
        const first = results.find((result) => result.status === "rejected");
        toast.error(`Couldn't delete ${failed} item${failed === 1 ? "" : "s"}`, {
          description: first && first.status === "rejected" ? errorText(first.reason, "") : undefined,
        });
      }
      return ids;
    },
    [removeItems, invalidateTransactions, restoreItems],
  );

  return { setQuantity, saveFields, createItem, deleteItems, restoreItems, reportFailure };
}
