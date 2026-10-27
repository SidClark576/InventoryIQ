import { BarcodeIcon, MagnifyingGlassIcon, PackageIcon, PlusIcon, UploadSimpleIcon } from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

/** Header plus six rows shaped like real ones (name, category, quantity block). */
export function StockSkeleton() {
  return (
    <div role="status" aria-busy="true" className="overflow-hidden rounded-3xl border border-border bg-card">
      <span className="sr-only">Loading stock</span>
      <div className="flex h-10 items-center justify-between border-b border-border px-4 text-xs font-medium text-muted-foreground">
        <span>Item</span>
        <span>On hand</span>
      </div>
      {Array.from({ length: 6 }, (_, index) => (
        <div key={index} className="flex items-center gap-4 border-t border-border/70 px-4 py-3 first:border-t-0">
          <div className="flex min-w-0 flex-1 flex-col gap-2">
            <Skeleton className="h-4 w-2/5" />
            <Skeleton className="h-3 w-1/4" />
          </div>
          <Skeleton className="h-8 w-28 touch:h-11" />
        </div>
      ))}
    </div>
  );
}

export function StockError({ onRetry }: { onRetry: () => void }) {
  return (
    <div role="alert" className="flex flex-wrap items-center gap-3 rounded-3xl border border-destructive/30 bg-destructive/5 px-5 py-4 text-sm">
      <span className="text-destructive">Can't reach Panindo. Check your connection.</span>
      <Button type="button" variant="outline" size="sm" onClick={onRetry}>
        Retry
      </Button>
    </div>
  );
}

export function NoMatches({ onClear }: { onClear: () => void }) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-3xl border border-dashed border-border px-6 py-14 text-center">
      <MagnifyingGlassIcon className="size-8 text-muted-foreground" />
      <p className="font-medium">No items match</p>
      <p className="text-sm text-muted-foreground">Try another search or status.</p>
      <Button type="button" variant="outline" onClick={onClear}>
        Clear filters
      </Button>
    </div>
  );
}

type EmptyShelfProps = {
  canEdit: boolean;
  importAvailable: boolean;
  onAdd: () => void;
  onScan: () => void;
  onImport: () => void;
};

export function EmptyShelf({ canEdit, importAvailable, onAdd, onScan, onImport }: EmptyShelfProps) {
  return (
    <div className="flex flex-col items-center gap-5 rounded-3xl border border-dashed border-border px-6 py-14 text-center">
      <PackageIcon className="size-8 text-muted-foreground" />
      <p className="font-heading text-lg font-semibold">
        Your shelf is empty. {canEdit ? "Let's fill it." : "Ask an owner or editor to add items."}
      </p>
      {canEdit ? (
        <div className="flex w-full max-w-md flex-col gap-2 sm:flex-row sm:justify-center">
          <Button type="button" size="lg" className="min-h-11" onClick={onAdd}>
            <PlusIcon />
            Add item
          </Button>
          <Button type="button" variant="outline" size="lg" className="min-h-11" onClick={onScan}>
            <BarcodeIcon />
            Scan
          </Button>
          {importAvailable ? (
            <Button type="button" variant="outline" size="lg" className="min-h-11" onClick={onImport}>
              <UploadSimpleIcon />
              Import CSV
            </Button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
