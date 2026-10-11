import { useEffect, useState } from "react";
import { TrashIcon } from "@phosphor-icons/react";
import { toast } from "sonner";
import { deleteCategory } from "@/api";
import { useInventory } from "@/app/inventory-store";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { plural } from "@/lib/format";
import { errorText } from "@/lib/errors";

const DEFAULT_CATEGORY = "Uncategorized";

type CategoriesDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

/**
 * Categories exist through items (there is no create endpoint), so this lists them
 * with item counts and deletes. Deleting moves its items to "Uncategorized".
 */
export function CategoriesDialog({ open, onOpenChange }: CategoriesDialogProps) {
  const { categories, items, loadCategories, reloadItems } = useInventory();
  const [pending, setPending] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) void loadCategories();
  }, [open, loadCategories]);

  const countOf = (category: string) =>
    items.filter((item) => (item.category || DEFAULT_CATEGORY) === category).length;

  async function confirmDelete() {
    if (!pending) return;
    setBusy(true);
    try {
      await deleteCategory(pending);
      toast.success(`Deleted ${pending}`, { description: `Its items moved to ${DEFAULT_CATEGORY}.` });
      await Promise.all([reloadItems(), loadCategories()]);
    } catch (err: unknown) {
      toast.error(`Couldn't delete ${pending}`, {
        description: errorText(err, "Try again."),
      });
    } finally {
      setBusy(false);
      setPending(null);
    }
  }

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-h-[85svh] grid-rows-[auto_minmax(0,1fr)] sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Manage categories</DialogTitle>
            <DialogDescription>
              New categories appear when you give an item one. Deleting a category moves its items to {DEFAULT_CATEGORY}.
            </DialogDescription>
          </DialogHeader>
          <ul id="categories-list" className="min-h-0 divide-y divide-border overflow-y-auto rounded-2xl border border-border">
            {categories.length === 0 ? (
              <li id="no-categories" className="px-4 py-6 text-sm text-muted-foreground">
                No categories yet.
              </li>
            ) : (
              categories.map((category) => {
                const isDefault = category.toLowerCase() === DEFAULT_CATEGORY.toLowerCase();
                return (
                  <li key={category} className="flex items-center gap-3 px-4 py-2">
                    <span className="min-w-0 flex-1 truncate text-sm font-medium">{category}</span>
                    <span className="text-xs text-muted-foreground tabular-nums">{plural(countOf(category), "item")}</span>
                    {isDefault ? (
                      <span className="px-1 text-xs text-muted-foreground">Default</span>
                    ) : (
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon-sm"
                        aria-label={`Delete ${category}`}
                        onClick={() => setPending(category)}
                      >
                        <TrashIcon />
                      </Button>
                    )}
                  </li>
                );
              })
            )}
          </ul>
        </DialogContent>
      </Dialog>
      <ConfirmDialog
        open={pending !== null}
        onOpenChange={(next) => {
          if (!next) setPending(null);
        }}
        title={`Delete ${pending ?? "category"}?`}
        description={`${plural(pending ? countOf(pending) : 0, "item")} will move to ${DEFAULT_CATEGORY}.`}
        confirmLabel="Delete category"
        busy={busy}
        onConfirm={() => void confirmDelete()}
      />
    </>
  );
}
