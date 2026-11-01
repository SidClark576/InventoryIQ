import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  ensureOrgContext,
  getAllItems,
  getCategories,
  getTransactions,
  type InventoryItem,
} from "@/api";
import { parseTransactions, type Transaction } from "@/lib/activity";
import { quantityOf } from "@/lib/dashboardStats";
import { createQuantityQueue, type QuantityQueue } from "@/lib/quantity-queue";
import { getCurrentOrg } from "@/session";
import { errorText } from "@/lib/errors";

export type LoadStatus = "idle" | "loading" | "ready" | "error";

export type InventoryStore = {
  items: InventoryItem[];
  itemsStatus: LoadStatus;
  itemsError: string | null;
  reloadItems: () => Promise<void>;
  upsertItem: (item: InventoryItem) => void;
  removeItems: (itemIDs: readonly string[]) => void;
  transactions: Transaction[];
  txStatus: LoadStatus;
  txError: string | null;
  /** Loads GET /transactions once; `force` refetches. */
  loadTransactions: (force?: boolean) => Promise<void>;
  /** Refetches transactions only if a screen already asked for them. */
  invalidateTransactions: () => void;
  categories: string[];
  loadCategories: () => Promise<void>;
  /** Items with quantity taps not saved yet (or saving). Reloads keep their cached row. */
  pendingIDs: ReadonlySet<string>;
  quantityQueue: QuantityQueue;
  /** Moves the cached quantity now; the first tap on an item remembers its server row. */
  stageQuantity: (itemID: string, delta: number) => void;
  /** Last row the server confirmed (the cache shows it plus unsent taps); read at call time, safe in toasts. */
  serverItem: (itemID: string) => InventoryItem | undefined;
};

const InventoryContext = createContext<InventoryStore | null>(null);

export function useInventory(): InventoryStore {
  const value = useContext(InventoryContext);
  if (!value) throw new Error("useInventory must be used inside InventoryProvider");
  return value;
}


function mergeCategories(server: readonly string[], items: readonly InventoryItem[]): string[] {
  const fromItems = items.map((item) => item.category).filter((cat): cat is string => Boolean(cat));
  const seen = new Map<string, string>();
  for (const cat of [...server, ...fromItems]) {
    const key = cat.toLowerCase();
    if (!seen.has(key)) seen.set(key, cat);
  }
  return [...seen.values()].sort((a, b) => a.localeCompare(b));
}

/**
 * One cache of GET /items (and, on demand, GET /transactions) for the signed-in shell,
 * so Today, Stock and Activity share rows and the Today badge. Reloads on org switch.
 * Never calls GET /insights: that endpoint sends SNS/SQS messages on every request.
 */
export function InventoryProvider({ orgEpoch, children }: { orgEpoch: number; children: ReactNode }) {
  const [items, setItems] = useState<InventoryItem[]>([]);
  const [itemsStatus, setItemsStatus] = useState<LoadStatus>("idle");
  const [itemsError, setItemsError] = useState<string | null>(null);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [txStatus, setTxStatus] = useState<LoadStatus>("idle");
  const [txError, setTxError] = useState<string | null>(null);
  const [serverCategories, setServerCategories] = useState<string[]>([]);
  const itemsRef = useRef<InventoryItem[]>([]);
  const itemsGen = useRef(0);
  const txGen = useRef(0);
  const txRequested = useRef(false);

  const [pendingIDs, setPendingIDs] = useState<ReadonlySet<string>>(new Set());
  const serverRows = useRef(new Map<string, InventoryItem>());
  const pendingRef = useRef(pendingIDs);
  const [quantityQueue] = useState(() => {
    const queue = createQuantityQueue((id) => {
      const pending = queue.isPending(id);
      if (!pending) serverRows.current.delete(id);
      setPendingIDs((prev) => {
        if (prev.has(id) === pending) return prev;
        const next = new Set(prev);
        if (pending) next.add(id);
        else next.delete(id);
        return next;
      });
    });
    return queue;
  });

  itemsRef.current = items;
  pendingRef.current = pendingIDs;

  const reloadItems = useCallback(async () => {
    const gen = ++itemsGen.current;
    const mark = quantityQueue.mark();
    // Skeletons only on an empty cache; a background reload keeps rows (and open count inputs) mounted.
    setItemsStatus(itemsRef.current.length ? "ready" : "loading");
    setItemsError(null);
    try {
      await ensureOrgContext();
    } catch {
      // Org tables may not be deployed; requests then run without X-IQ-Org.
    }
    const orgID = getCurrentOrg();
    try {
      const rows = await getAllItems();
      if (gen !== itemsGen.current || getCurrentOrg() !== orgID) return;
      // Rows tapped after this GET started, or still saving, keep the cached copy; the next reload takes the server's.
      const keep = (id: string) => quantityQueue.isPending(id) || quantityQueue.tappedSince(id, mark);
      setItems((prev) => {
        const kept = new Map(prev.filter((row) => row.itemID && keep(row.itemID)).map((row) => [row.itemID, row]));
        return kept.size ? rows.map((row) => kept.get(row.itemID) ?? row) : rows;
      });
      setItemsStatus("ready");
    } catch (err: unknown) {
      if (gen !== itemsGen.current) return;
      setItemsError(errorText(err, "Failed to load items"));
      setItemsStatus("error");
    }
  }, [quantityQueue]);

  const loadTransactions = useCallback(async (force = false) => {
    txRequested.current = true;
    if (!force && txGen.current > 0) return;
    const gen = ++txGen.current;
    setTxStatus("loading");
    setTxError(null);
    try {
      const rows = parseTransactions(await getTransactions());
      if (gen !== txGen.current) return;
      setTransactions(rows);
      setTxStatus("ready");
    } catch (err: unknown) {
      if (gen !== txGen.current) return;
      setTxError(errorText(err, "Failed to load activity"));
      setTxStatus("error");
    }
  }, []);

  const invalidateTransactions = useCallback(() => {
    if (txRequested.current) void loadTransactions(true);
  }, [loadTransactions]);

  const loadCategories = useCallback(async () => {
    try {
      setServerCategories(await getCategories());
    } catch {
      // Categories also come from item rows, so a failed call still leaves a usable list.
    }
  }, []);

  // Child screens' effects run before this one, so only clear on a real org switch;
  // clearing on mount would discard a transactions request a screen just started.
  const loadedEpoch = useRef<number | null>(null);
  useEffect(() => {
    const switched = loadedEpoch.current !== null && loadedEpoch.current !== orgEpoch;
    loadedEpoch.current = orgEpoch;
    if (switched) {
      // ponytail: taps not sent yet are dropped on an org switch; they would otherwise PUT into the new org.
      quantityQueue.cancelAll();
      serverRows.current.clear();
      itemsRef.current = [];
      setItems([]);
      setTransactions([]);
      setServerCategories([]);
      setTxStatus("idle");
      // txGen keeps counting so a late response for the old org can never match a new generation.
      if (txRequested.current) void loadTransactions(true);
    }
    void reloadItems();
  }, [orgEpoch, reloadItems, loadTransactions, quantityQueue]);

  // Closing the tab mid-batch: send the taps now, and ask the browser to hold the page while they save.
  useEffect(() => {
    const flush = () => quantityQueue.flushAll();
    const warn = (event: BeforeUnloadEvent) => {
      if (!pendingRef.current.size) return;
      flush();
      event.preventDefault();
    };
    window.addEventListener("beforeunload", warn);
    window.addEventListener("pagehide", flush);
    return () => {
      window.removeEventListener("beforeunload", warn);
      window.removeEventListener("pagehide", flush);
    };
  }, [quantityQueue]);

  const serverItem = useCallback(
    (itemID: string) => serverRows.current.get(itemID) ?? itemsRef.current.find((item) => item.itemID === itemID),
    [],
  );

  const stageQuantity = useCallback(
    (itemID: string, delta: number) => {
      const row = itemsRef.current.find((item) => item.itemID === itemID);
      if (row && !quantityQueue.isPending(itemID)) serverRows.current.set(itemID, row);
      setItems((prev) =>
        prev.map((item) => (item.itemID === itemID ? { ...item, quantity: Math.max(0, quantityOf(item) + delta) } : item)),
      );
    },
    [quantityQueue],
  );

  /** `saved` is a server row; taps on it not sent yet stay on top of its quantity. */
  const upsertItem = useCallback((saved: InventoryItem) => {
    const id = saved.itemID;
    if (id && quantityQueue.isPending(id)) serverRows.current.set(id, saved);
    const unsent = id ? quantityQueue.unsent(id) : 0;
    const next = unsent ? { ...saved, quantity: Math.max(0, quantityOf(saved) + unsent) } : saved;
    setItems((prev) => {
      const exists = prev.some((item) => item.itemID === next.itemID);
      return exists
        ? prev.map((item) => (item.itemID === next.itemID ? next : item))
        : [next, ...prev];
    });
  }, [quantityQueue]);

  const removeItems = useCallback((itemIDs: readonly string[]) => {
    const drop = new Set(itemIDs);
    setItems((prev) => prev.filter((item) => !item.itemID || !drop.has(item.itemID)));
  }, []);

  const categories = useMemo(() => mergeCategories(serverCategories, items), [serverCategories, items]);

  const value = useMemo<InventoryStore>(
    () => ({
      items,
      itemsStatus,
      itemsError,
      reloadItems,
      upsertItem,
      removeItems,
      transactions,
      txStatus,
      txError,
      loadTransactions,
      invalidateTransactions,
      categories,
      loadCategories,
      pendingIDs,
      quantityQueue,
      stageQuantity,
      serverItem,
    }),
    [
      items,
      itemsStatus,
      itemsError,
      reloadItems,
      upsertItem,
      removeItems,
      transactions,
      txStatus,
      txError,
      loadTransactions,
      invalidateTransactions,
      categories,
      loadCategories,
      pendingIDs,
      quantityQueue,
      stageQuantity,
      serverItem,
    ],
  );

  return <InventoryContext.Provider value={value}>{children}</InventoryContext.Provider>;
}
