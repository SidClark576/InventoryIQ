import { useState, type FormEvent } from "react";
import { BarcodeIcon } from "@phosphor-icons/react";
import { lookupBarcode, type InventoryItem } from "@/api";
import { useInventory } from "@/app/inventory-store";
import { useStockActions } from "@/app/use-stock-actions";
import { BarcodeScanDialog } from "@/components/barcode-scan-dialog";
import { Field, TEXTAREA_CLASS } from "@/components/field";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { getEditItem } from "@/session";

type Draft = {
  name: string;
  category: string;
  quantity: string;
  threshold: string;
  price: string;
  barcode: string;
  description: string;
};

const EMPTY: Draft = {
  name: "",
  category: "",
  quantity: "0",
  threshold: "10",
  price: "",
  barcode: "",
  description: "",
};

function text(value: unknown): string {
  return value === null || value === undefined ? "" : String(value);
}

/** A Stock barcode scan leaves `{ name, category, barcode }` in sessionStorage before opening this sheet. */
function prefilled(): Draft {
  const raw = getEditItem();
  if (!raw) return EMPTY;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || "itemID" in parsed) return EMPTY;
    const prefill = parsed as Record<string, unknown>;
    return {
      ...EMPTY,
      name: text(prefill.name),
      category: text(prefill.category),
      barcode: text(prefill.barcode),
    };
  } catch {
    return EMPTY;
  }
}

type AddItemFormProps = {
  onDone: (created: InventoryItem | null) => void;
};

export function AddItemForm({ onDone }: AddItemFormProps) {
  const { categories } = useInventory();
  const { createItem } = useStockActions();
  const [draft, setDraft] = useState<Draft>(prefilled);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [scanOpen, setScanOpen] = useState(false);

  function patch(partial: Partial<Draft>) {
    setDraft((current) => ({ ...current, ...partial }));
  }

  async function onCode(code: string): Promise<string | void> {
    const product = await lookupBarcode(code);
    if (!product) {
      patch({ barcode: code });
      return `No product found for ${code}. The barcode is filled in; add the rest by hand.`;
    }
    setDraft((current) => ({
      ...current,
      barcode: code,
      name: product.name ? String(product.name) : current.name,
      category: product.category ? String(product.category) : current.category,
    }));
    setScanOpen(false);
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const name = draft.name.trim();
    const quantity = Number(draft.quantity || 0);
    const threshold = Number(draft.threshold || 0);
    const price = Number(draft.price || 0);
    if (!name) return setError("Give the item a name.");
    if (!Number.isInteger(quantity) || quantity < 0) return setError("Quantity must be a whole number, 0 or more.");
    if (!Number.isInteger(threshold) || threshold < 0) return setError("Low-stock alert must be a whole number, 0 or more.");
    if (!Number.isFinite(price) || price < 0) return setError("Price must be 0 or more.");
    setError("");
    setSaving(true);
    const created = await createItem({
      name,
      category: draft.category.trim(),
      quantity,
      lowStockThreshold: threshold,
      price,
      barcode: draft.barcode.trim(),
      description: draft.description.trim(),
    });
    setSaving(false);
    if (created) onDone(created);
  }

  return (
    <>
      <SheetHeader className="pr-14">
        <SheetTitle className="text-xl font-semibold">Add item</SheetTitle>
        <SheetDescription>Scan a barcode to fill in what we can find.</SheetDescription>
      </SheetHeader>
      <form className="grid grid-cols-2 gap-x-3 gap-y-4 px-6 pb-8" onSubmit={(event) => void onSubmit(event)} noValidate>
        <Field id="n-name" label="Name" className="col-span-2">
          <Input
            id="n-name"
            autoFocus
            value={draft.name}
            placeholder="e.g. Oat milk 1L"
            onChange={(event) => patch({ name: event.target.value })}
          />
        </Field>
        <Field id="n-barcode" label="Barcode" className="col-span-2">
          <div className="flex gap-2">
            <Input
              id="n-barcode"
              inputMode="numeric"
              autoComplete="off"
              value={draft.barcode}
              placeholder="Optional"
              onChange={(event) => patch({ barcode: event.target.value })}
            />
            <Button type="button" variant="outline" onClick={() => setScanOpen(true)}>
              <BarcodeIcon />
              Scan
            </Button>
          </div>
        </Field>
        <Field id="n-quantity" label="On hand" className="col-span-1">
          <Input
            id="n-quantity"
            type="number"
            min={0}
            step={1}
            inputMode="numeric"
            className="tabular-nums"
            value={draft.quantity}
            onChange={(event) => patch({ quantity: event.target.value })}
          />
        </Field>
        <Field id="n-threshold" label="Low-stock alert at" className="col-span-1">
          <Input
            id="n-threshold"
            type="number"
            min={0}
            step={1}
            inputMode="numeric"
            className="tabular-nums"
            value={draft.threshold}
            onChange={(event) => patch({ threshold: event.target.value })}
          />
        </Field>
        <Field id="n-category" label="Category" className="col-span-1">
          <Input
            id="n-category"
            list="add-item-categories"
            autoComplete="off"
            placeholder="Uncategorized"
            value={draft.category}
            onChange={(event) => patch({ category: event.target.value })}
          />
          <datalist id="add-item-categories">
            {categories.map((category) => (
              <option key={category} value={category} />
            ))}
          </datalist>
        </Field>
        <Field id="n-price" label="Unit price ($)" className="col-span-1">
          <Input
            id="n-price"
            type="number"
            min={0}
            step="0.01"
            inputMode="decimal"
            placeholder="0.00"
            className="tabular-nums"
            value={draft.price}
            onChange={(event) => patch({ price: event.target.value })}
          />
        </Field>
        <Field id="n-description" label="Description" className="col-span-2">
          <textarea
            id="n-description"
            className={TEXTAREA_CLASS}
            placeholder="Optional"
            value={draft.description}
            onChange={(event) => patch({ description: event.target.value })}
          />
        </Field>
        {error ? (
          <p role="alert" className="col-span-2 text-sm text-destructive">
            {error}
          </p>
        ) : null}
        <div className="col-span-2 flex gap-2">
          <Button type="submit" size="lg" className="flex-1" disabled={saving}>
            {saving ? "Adding…" : "Add item"}
          </Button>
          <Button type="button" size="lg" variant="outline" onClick={() => onDone(null)}>
            Cancel
          </Button>
        </div>
      </form>
      <BarcodeScanDialog
        open={scanOpen}
        onOpenChange={setScanOpen}
        description="Fill in this item from its barcode."
        onCode={onCode}
      />
    </>
  );
}
