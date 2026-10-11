import {
  ArrowCounterClockwiseIcon,
  BarcodeIcon,
  DotsThreeIcon,
  DownloadSimpleIcon,
  ListChecksIcon,
  MagnifyingGlassIcon,
  PrinterIcon,
  TagIcon,
  UploadSimpleIcon,
} from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import { useDebouncedInput } from "@/hooks/use-debounced-input";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import type { Grouping } from "./stock-view";

type StockToolbarProps = {
  query: string;
  onQuery: (value: string) => void;
  grouping: Grouping;
  onGrouping: (value: Grouping) => void;
  counting: boolean;
  onCount: () => void;
  onScan: () => void;
  onCategories: () => void;
  onImport: () => void;
  importAvailable: boolean;
  onExport: () => void;
  onPrint: () => void;
  onTrash: () => void;
  /** Viewers get search, scan, export and print only. */
  canEdit: boolean;
};

export function StockToolbar({
  query,
  onQuery,
  grouping,
  onGrouping,
  counting,
  onCount,
  onScan,
  onCategories,
  onImport,
  importAvailable,
  onExport,
  onPrint,
  onTrash,
  canEdit,
}: StockToolbarProps) {
  const [search, setSearch] = useDebouncedInput(query, onQuery);
  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
      <div className="relative min-w-0 flex-1 sm:max-w-sm">
        <MagnifyingGlassIcon className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          id="inv-search"
          type="search"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search name, category or barcode"
          aria-label="Search stock"
          className="pl-9"
        />
      </div>
      <div className="flex flex-wrap items-center gap-2 sm:ml-auto">
        <ToggleGroup
          aria-label="Group by"
          value={[grouping]}
          onValueChange={(value) => {
            const next = value[0];
            if (next === "status" || next === "category") onGrouping(next);
          }}
          variant="outline"
          size="sm"
          spacing={0}
        >
          <ToggleGroupItem value="status" className="aria-pressed:bg-muted aria-pressed:text-foreground">
            Status
          </ToggleGroupItem>
          <ToggleGroupItem value="category" className="aria-pressed:bg-muted aria-pressed:text-foreground">
            Category
          </ToggleGroupItem>
        </ToggleGroup>
        <Button id="btn-scan" type="button" variant="outline" size="sm" onClick={onScan} disabled={counting}>
          <BarcodeIcon />
          Scan
        </Button>
        {canEdit ? (
          <Button
            id="btn-count"
            type="button"
            variant={counting ? "default" : "outline"}
            size="sm"
            aria-pressed={counting}
            onClick={onCount}
          >
            <ListChecksIcon />
            {counting ? "Counting…" : "Count stock"}
          </Button>
        ) : null}
        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <Button id="btn-inventory-more" type="button" variant="outline" size="sm" aria-label="More stock actions" />
            }
          >
            <DotsThreeIcon weight="bold" />
            More
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56">
            {canEdit ? (
              <>
                <DropdownMenuItem id="btn-manage-categories" onClick={onCategories}>
                  <TagIcon />
                  Manage categories
                </DropdownMenuItem>
                <DropdownMenuItem id="btn-bulk-import" onClick={onImport} disabled={!importAvailable}>
                  <UploadSimpleIcon />
                  {importAvailable ? "Import CSV" : "Import CSV (not available)"}
                </DropdownMenuItem>
              </>
            ) : null}
            <DropdownMenuItem onClick={onExport}>
              <DownloadSimpleIcon />
              Export CSV
            </DropdownMenuItem>
            <DropdownMenuItem onClick={onPrint}>
              <PrinterIcon />
              Print report
            </DropdownMenuItem>
            {canEdit ? (
              <>
                <DropdownMenuSeparator />
                <DropdownMenuItem id="btn-show-deleted" onClick={onTrash}>
                  <ArrowCounterClockwiseIcon />
                  Show deleted
                </DropdownMenuItem>
              </>
            ) : null}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>
  );
}
