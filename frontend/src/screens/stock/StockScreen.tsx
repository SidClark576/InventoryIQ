import { useEffect, useMemo, useState } from "react";
import { flushSync } from "react-dom";
import { PlusIcon } from "@phosphor-icons/react";
import { toast } from "sonner";
import { lookupBarcode, type InventoryItem } from "@/api";
import { useOrgShell } from "@/app/AppLayout";
import { useInventory } from "@/app/inventory-store";
import { useSheetParams } from "@/app/use-sheet-params";
import { useStockActions } from "@/app/use-stock-actions";
import { BarcodeScanDialog } from "@/components/barcode-scan-dialog";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { ItemSheetHost } from "@/components/item-sheet/ItemSheetHost";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { useIsDesktop } from "@/hooks/use-media-query";
import { countByLevel, deriveDashStats } from "@/lib/dashboardStats";
import { plural } from "@/lib/format";
import { setEditItem } from "@/session";
import { CategoriesDialog } from "./CategoriesDialog";
import { summarizeCount, type Counts } from "./count";
import { CountCards } from "./CountCards";
import { CountReviewDialog } from "./CountReviewDialog";
import { downloadItemsCsv } from "./export";
import { CountBar, SelectionBar } from "./FloatingBar";
import { HealthBar } from "./HealthBar";
import { ImportDialog } from "./ImportDialog";
import { PrintReport } from "./PrintReport";
import { EmptyShelf, NoMatches, StockError, StockSkeleton } from "./StockStates";
import { StockTable } from "./StockTable";
import { StockToolbar } from "./StockToolbar";
import { filterItems, groupItems, useStockView } from "./stock-view";
import { TrashView } from "./TrashView";
import { useRowStepper } from "./use-row-stepper";

type DialogName = "scan" | "categories" | "import" | "review" | "bulk-delete" | "stop-count" | null;

export function StockScreen() {
  const { items, itemsStatus, reloadItems } = useInventory();
  const { deleteItems } = useStockActions();
  const { canEdit, orgEpoch } = useOrgShell();
  const { openItem, openNew, itemHref } = useSheetParams();
  const view = useStockView();
  const stepper = useRowStepper();
  const isDesktop = useIsDesktop();
  const [collapsed, setCollapsed] = useState<ReadonlySet<string>>(new Set());
  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set());
  const [counting, setCounting] = useState(false);
  const [counts, setCounts] = useState<Counts>({});
  const [dialog, setDialog] = useState<DialogName>(null);
  const [busy, setBusy] = useState(false);
  const [importAvailable, setImportAvailable] = useState(true);
  const [printing, setPrinting] = useState(false);

  useEffect(() => {
    document.title = "Stock | Panindo";
  }, []);

  // A 403/404 from the import routes is per org; another org may have them.
  useEffect(() => {
    setImportAvailable(true);
  }, [orgEpoch]);

  // Print styles key off this attribute (index.css); keep it set, and the report mounted, only while printing.
  // flushSync renders the report before the browser snapshots the page.
  useEffect(() => {
    const arm = () => {
      document.documentElement.dataset.iqPrint = "inventory";
      flushSync(() => setPrinting(true));
    };
    const clear = () => {
      delete document.documentElement.dataset.iqPrint;
      setPrinting(false);
    };
    window.addEventListener("beforeprint", arm);
    window.addEventListener("afterprint", clear);
    return () => {
      window.removeEventListener("beforeprint", arm);
      window.removeEventListener("afterprint", clear);
      clear();
    };
  }, []);

  const loading = itemsStatus === "idle" || itemsStatus === "loading";
  const levelCounts = useMemo(() => countByLevel(items), [items]);
  const value = useMemo(() => deriveDashStats(items).estimatedInventoryValue, [items]);
  const rows = useMemo(() => filterItems(items, view.status, view.query), [items, view.status, view.query]);
  const groups = useMemo(() => groupItems(rows, view.grouping), [rows, view.grouping]);
  const countSummary = useMemo(() => summarizeCount(items, counts), [items, counts]);
  // Bulk actions only touch selected rows the current filters show.
  const selectedItems = useMemo(
    () => rows.filter((item) => item.itemID && selected.has(item.itemID)),
    [rows, selected],
  );
  const filtered = view.status !== "all" || view.query.trim() !== "";

  // Drop selections for rows that disappeared (deleted elsewhere, org switch).
  useEffect(() => {
    setSelected((prev) => {
      const live = new Set(items.flatMap((item) => (item.itemID ? [item.itemID] : [])));
      const next = new Set([...prev].filter((id) => live.has(id)));
      return next.size === prev.size ? prev : next;
    });
  }, [items]);

  function select(ids: readonly string[], checked: boolean) {
    setSelected((prev) => {
      const next = new Set(prev);
      for (const id of ids) {
        if (checked) next.add(id);
        else next.delete(id);
      }
      return next;
    });
  }

  function toggleGroup(key: string) {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function stopCounting() {
    setDialog(null);
    setCounting(false);
    setCounts({});
  }

  function toggleCounting() {
    if (counting) {
      if (countSummary.counted > 0) setDialog("stop-count");
      else stopCounting();
      return;
    }
    setSelected(new Set());
    setCounts({});
    setCounting(true);
  }

  function exportCsv(targets: readonly InventoryItem[], suffix = "") {
    if (targets.length === 0) {
      toast.warning("Nothing to export", { description: "Add items first." });
      return;
    }
    downloadItemsCsv(targets, suffix);
    toast.success(`Exported ${plural(targets.length, "item")}`);
  }

  function print() {
    if (items.length === 0) {
      toast.warning("Nothing to print", { description: "Add items first." });
      return;
    }
    document.documentElement.dataset.iqPrint = "inventory";
    flushSync(() => setPrinting(true));
    window.print();
  }

  async function onScanCode(code: string): Promise<string | void> {
    const match = items.find((item) => item.barcode === code);
    if (match?.itemID) {
      setDialog(null);
      openItem(match.itemID);
      return;
    }
    if (!canEdit) return `No item in stock has barcode ${code}.`;
    const product = await lookupBarcode(code);
    setEditItem(
      JSON.stringify(
        product
          ? { name: product.name ? String(product.name) : "", category: product.category ? String(product.category) : "", barcode: code }
          : { barcode: code },
      ),
    );
    setDialog(null);
    if (!product) toast(`No product found for ${code}`, { description: "Add it with the barcode filled in." });
    openNew();
  }

  async function bulkDelete() {
    setBusy(true);
    const deleted = new Set(await deleteItems(selectedItems));
    setBusy(false);
    setDialog(null);
    // Rows that failed stay selected so a retry is one click.
    setSelected(new Set(selectedItems.flatMap((item) => (item.itemID && !deleted.has(item.itemID) ? [item.itemID] : []))));
  }

  function finishCount(failedIDs: readonly string[]) {
    setDialog(null);
    if (failedIDs.length) {
      // Keep counting with only the rows that did not save, so they can be reviewed again.
      setCounts((prev) => Object.fromEntries(failedIDs.flatMap((id) => (id in prev ? [[id, prev[id]!]] : []))));
      return;
    }
    setCounting(false);
    setCounts({});
  }

  if (view.trash) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader title="Stock" />
        <TrashView onBack={() => view.setTrash(false)} />
      </div>
    );
  }

  return (
    <>
      <div data-inventory-ui className="flex flex-col gap-5">
        <PageHeader
          title="Stock"
          description={counting ? "Count each shelf and type what you see. Blank means not counted." : undefined}
          actions={
            canEdit ? (
              <Button id="btn-add-new" type="button" onClick={openNew} disabled={counting}>
                <PlusIcon />
                Add item
              </Button>
            ) : undefined
          }
        />

        {itemsStatus === "ready" ? (
          <HealthBar counts={levelCounts} total={items.length} value={value} status={view.status} onStatus={view.setStatus} />
        ) : null}

        <StockToolbar
          query={view.query}
          onQuery={view.setQuery}
          grouping={view.grouping}
          onGrouping={view.setGrouping}
          counting={counting}
          onCount={toggleCounting}
          onScan={() => setDialog("scan")}
          onCategories={() => setDialog("categories")}
          onImport={() => setDialog("import")}
          importAvailable={importAvailable}
          onExport={() => exportCsv(items)}
          onPrint={print}
          onTrash={() => view.setTrash(true)}
          canEdit={canEdit}
        />

        {filtered && !loading && items.length > 0 ? (
          <p className="-mt-2 text-sm text-muted-foreground" aria-live="polite">
            <span id="pagination-text" className="tabular-nums">
              {rows.length} of {plural(items.length, "item")} shown
            </span>
            {" · "}
            <button
              type="button"
              className="rounded-sm font-medium text-foreground underline decoration-muted-foreground underline-offset-4 outline-none hover:decoration-foreground focus-visible:ring-[3px] focus-visible:ring-ring/50"
              onClick={view.clearFilters}
            >
              Clear filters
            </button>
          </p>
        ) : null}

        {itemsStatus === "error" ? <StockError onRetry={() => void reloadItems()} /> : null}
        {loading ? (
          <StockSkeleton />
        ) : rows.length === 0 ? (
          items.length ? (
            <NoMatches onClear={view.clearFilters} />
          ) : itemsStatus === "error" ? null : (
            <EmptyShelf
              canEdit={canEdit}
              importAvailable={importAvailable}
              onAdd={openNew}
              onScan={() => setDialog("scan")}
              onImport={() => setDialog("import")}
            />
          )
        ) : counting && !isDesktop ? (
          <CountCards
            groups={groups}
            counts={counts}
            onCount={(id, raw) => setCounts((prev) => ({ ...prev, [id]: raw }))}
            onReview={() => {
              if (countSummary.counted > 0) setDialog("review");
            }}
          />
        ) : (
          <StockTable
            groups={groups}
            collapsed={collapsed}
            onToggleGroup={toggleGroup}
            selected={selected}
            onSelect={select}
            counting={counting}
            counts={counts}
            onCount={(id, raw) => setCounts((prev) => ({ ...prev, [id]: raw }))}
            itemHref={itemHref}
            canEdit={canEdit}
            pending={stepper.pending}
            onStep={stepper.step}
            selecting={selectedItems.length > 0}
          />
        )}

        {counting || selectedItems.length > 0 ? <div aria-hidden className="h-16" /> : null}

        {counting ? (
          <CountBar
            counted={countSummary.counted}
            total={items.length}
            onCancel={toggleCounting}
            onReview={() => setDialog("review")}
          />
        ) : selectedItems.length > 0 ? (
          <SelectionBar
            count={selectedItems.length}
            canEdit={canEdit}
            onExport={() => exportCsv(selectedItems, "_selected")}
            onDelete={() => setDialog("bulk-delete")}
            onClear={() => setSelected(new Set())}
          />
        ) : null}
      </div>

      {printing ? <PrintReport items={items} /> : null}

      <BarcodeScanDialog
        open={dialog === "scan"}
        onOpenChange={(open) => setDialog(open ? "scan" : null)}
        description="Find an item by barcode, or start adding a new one."
        onCode={onScanCode}
      />
      <CategoriesDialog open={dialog === "categories"} onOpenChange={(open) => setDialog(open ? "categories" : null)} />
      <ImportDialog
        open={dialog === "import"}
        onOpenChange={(open) => setDialog(open ? "import" : null)}
        onUnavailable={() => setImportAvailable(false)}
      />
      <CountReviewDialog
        open={dialog === "review"}
        onOpenChange={(open) => setDialog(open ? "review" : null)}
        counted={countSummary.counted}
        total={items.length}
        changes={countSummary.changes}
        onFinished={finishCount}
      />
      <ConfirmDialog
        open={dialog === "bulk-delete"}
        onOpenChange={(open) => setDialog(open ? "bulk-delete" : null)}
        title={`Delete ${plural(selectedItems.length, "item")}?`}
        description="They move to deleted items. You can restore them for 30 days."
        confirmLabel="Delete"
        busy={busy}
        onConfirm={() => void bulkDelete()}
      />
      <ConfirmDialog
        open={dialog === "stop-count"}
        onOpenChange={(open) => setDialog(open ? "stop-count" : null)}
        title="Stop counting?"
        description={`The ${plural(countSummary.counted, "count")} you entered will be lost.`}
        confirmLabel="Discard counts"
        onConfirm={stopCounting}
      />
      <ItemSheetHost />
    </>
  );
}
