import { useRef } from "react";
import type { InventoryItem } from "@/api";
import { useInventory } from "@/app/inventory-store";
import { useSheetParams } from "@/app/use-sheet-params";
import { Button } from "@/components/ui/button";
import { Drawer, DrawerContent } from "@/components/ui/drawer";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { useIsDesktop } from "@/hooks/use-media-query";
import { clearEditItem } from "@/session";
import { AddItemForm } from "./AddItemForm";
import { ItemPanel } from "./ItemPanel";

/**
 * Item detail / add item, driven by `?item=<id>` and `?new=1` on the current route.
 * Side panel from 768px, swipe-to-close bottom drawer below.
 */
export function ItemSheetHost() {
  const { itemID, isNew, close } = useSheetParams();
  const { items, itemsStatus } = useInventory();
  const wide = useIsDesktop();
  const open = isNew || Boolean(itemID);
  // Pick Sheet or Drawer when it opens; rotating across 768px while open would remount the body and lose typing.
  const layout = useRef(wide);
  if (!open) layout.current = wide;
  const desktop = layout.current;
  const found = itemID ? items.find((row) => row.itemID === itemID) : undefined;

  // While the sheet animates closed (URL already cleared) or right after a delete removed the row,
  // keep rendering what was last on screen instead of flashing "Item not found".
  const last = useRef<{ isNew: boolean; itemID: string | null; item: InventoryItem | undefined }>({
    isNew: false,
    itemID: null,
    item: undefined,
  });
  const keptItem = last.current.itemID === itemID ? last.current.item : undefined;
  const shown = open ? { isNew, itemID, item: found ?? keptItem } : last.current;
  last.current = shown;
  const item = shown.item;
  const waiting = itemsStatus === "idle" || itemsStatus === "loading";

  function dismiss() {
    // A barcode prefill only applies to the add sheet it was opened for.
    if (isNew) clearEditItem();
    close();
  }

  const body = shown.isNew ? (
    <AddItemForm onDone={dismiss} />
  ) : item ? (
    <ItemPanel key={shown.itemID} item={item} onDeleted={close} />
  ) : waiting ? (
    <div className="flex flex-col gap-4 p-6">
      <SheetTitle className="sr-only">Loading item</SheetTitle>
      <Skeleton className="h-6 w-40" />
      <Skeleton className="h-28 w-full rounded-3xl" />
      <Skeleton className="h-10 w-full" />
    </div>
  ) : (
    <SheetHeader className="pr-14">
      <SheetTitle>Item not found</SheetTitle>
      <SheetDescription>
        It may have been deleted, or it belongs to another organization.
      </SheetDescription>
      <Button type="button" variant="outline" className="mt-4 self-start" onClick={close}>
        Close
      </Button>
    </SheetHeader>
  );
  const onOpenChange = (next: boolean) => {
    if (!next) dismiss();
  };

  return desktop ? (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="gap-0 overflow-y-auto overscroll-contain data-[side=right]:w-full data-[side=right]:sm:max-w-md"
      >
        {body}
      </SheetContent>
    </Sheet>
  ) : (
    <Drawer open={open} onOpenChange={onOpenChange}>
      <DrawerContent>{body}</DrawerContent>
    </Drawer>
  );
}
