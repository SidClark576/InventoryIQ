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
import { getCurrentOrg } from "@/session";
import { errorText } from "@/lib/errors";

export type LoadStatus = "idle" | "loading" | "ready" | "error";

export type InventoryStore = {
  items: InventoryItem[];
  itemsStatus: LoadStatus;
  itemsError: string | null;
  reloadItems: () => Promise<void>;
  /** Latest copy of one item, read at call time (safe inside toast callbacks). */
  getItem: (itemID: string) => InventoryItem | undefined;
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

  itemsRef.current = items;

  const reloadItems = useCallback(async () => {
    const gen = ++itemsGen.current;
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
      setItems(rows);
      setItemsStatus("ready");
    } catch (err: unknown) {
      if (gen !== itemsGen.current) return;
      setItemsError(errorText(err, "Failed to load items"));
      setItemsStatus("error");
    }
  }, []);

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
      itemsRef.current = [];
      setItems([]);
      setTransactions([]);
      setServerCategories([]);
      setTxStatus("idle");
      // txGen keeps counting so a late response for the old org can never match a new generation.
      if (txRequested.current) void loadTransactions(true);
    }
    void reloadItems();
  }, [orgEpoch, reloadItems, loadTransactions]);

  const getItem = useCallback(
    (itemID: string) => itemsRef.current.find((item) => item.itemID === itemID),
    [],
  );

  const upsertItem = useCallback((next: InventoryItem) => {
    setItems((prev) => {
      const exists = prev.some((item) => item.itemID === next.itemID);
      return exists
        ? prev.map((item) => (item.itemID === next.itemID ? next : item))
        : [next, ...prev];
    });
  }, []);

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
      getItem,
      upsertItem,
      removeItems,
      transactions,
      txStatus,
      txError,
      loadTransactions,
      invalidateTransactions,
      categories,
      loadCategories,
    }),
    [
      items,
      itemsStatus,
      itemsError,
      reloadItems,
      getItem,
      upsertItem,
      removeItems,
      transactions,
      txStatus,
      txError,
      loadTransactions,
      invalidateTransactions,
      categories,
      loadCategories,
    ],
  );

  return <InventoryContext.Provider value={value}>{children}</InventoryContext.Provider>;
}
