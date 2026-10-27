import {
  ArrowCounterClockwiseIcon,
  BarcodeIcon,
  DotsThreeIcon,
  DownloadSimpleIcon,
  ListChecksIcon,
  MagnifyingGlassIcon,
  PrinterIcon,
  SquaresFourIcon,
  TagIcon,
  UploadSimpleIcon,
  XIcon,
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
  return (
    // One sticky row: below the phone top bar (3.5rem) under md, at the page top from md.
    <div className="sticky top-[calc(3.5rem+env(safe-area-inset-top))] z-20 -mx-4 -my-2 flex items-center gap-2 bg-background px-4 py-2 md:top-0 md:mx-0 md:px-0">
      <SearchField query={query} onQuery={onQuery} />
      <div className="flex items-center gap-2 md:ml-auto">
        <ToggleGroup
          className="hidden md:flex"
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
        <Button
          id="btn-scan"
          type="button"
          variant="outline"
          size="sm"
          aria-label="Scan barcode"
          className="touch:min-w-11"
          onClick={onScan}
          disabled={counting}
        >
          <BarcodeIcon />
          <span className="hidden md:inline">Scan</span>
        </Button>
        {canEdit ? (
          <Button
            id="btn-count"
            type="button"
            variant={counting ? "default" : "outline"}
            size="sm"
            aria-pressed={counting}
            className="hidden md:inline-flex"
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
            <PhoneMenuItems canEdit={canEdit} counting={counting} onCount={onCount} grouping={grouping} onGrouping={onGrouping} />
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

function SearchField({ query, onQuery }: { query: string; onQuery: (value: string) => void }) {
  const [search, setSearch] = useDebouncedInput(query, onQuery);
  return (
    <div className="relative min-w-0 flex-1 md:max-w-sm">
      <MagnifyingGlassIcon className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
      <Input
        id="inv-search"
        type="search"
        enterKeyHint="search"
        value={search}
        onChange={(event) => setSearch(event.target.value)}
        placeholder="Search name, category or barcode"
        aria-label="Search stock"
        className="pr-10 pl-9 [&::-webkit-search-cancel-button]:hidden"
      />
      {search ? (
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          aria-label="Clear search"
          className="absolute top-1/2 right-0.5 -translate-y-1/2"
          onClick={() => {
            setSearch("");
            onQuery("");
          }}
        >
          <XIcon />
        </Button>
      ) : null}
    </div>
  );
}

type PhoneMenuItemsProps = Pick<StockToolbarProps, "canEdit" | "counting" | "onCount" | "grouping" | "onGrouping">;

/** Under md the toolbar is one row: Count stock and Group by live in More. */
function PhoneMenuItems({ canEdit, counting, onCount, grouping, onGrouping }: PhoneMenuItemsProps) {
  const other: Grouping = grouping === "category" ? "status" : "category";
  return (
    <>
      {canEdit ? (
        <DropdownMenuItem className="md:hidden" onClick={onCount}>
          <ListChecksIcon />
          {counting ? "Stop counting" : "Count stock"}
        </DropdownMenuItem>
      ) : null}
      <DropdownMenuItem className="md:hidden" onClick={() => onGrouping(other)}>
        <SquaresFourIcon />
        Group by {other}
      </DropdownMenuItem>
      <DropdownMenuSeparator className="md:hidden" />
    </>
  );
}
