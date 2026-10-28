import { useState, type FormEvent } from "react";
import type { InventoryItem } from "@/api";
import { useInventory } from "@/app/inventory-store";
import { useStockActions, type ItemFields } from "@/app/use-stock-actions";
import { Field, TEXTAREA_CLASS } from "@/components/field";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { priceOf, thresholdOf } from "@/lib/dashboardStats";
import { currencySymbol } from "@/lib/format";

type Draft = {
  name: string;
  category: string;
  price: string;
  threshold: string;
  barcode: string;
  description: string;
};

function draftOf(item: InventoryItem): Draft {
  return {
    name: item.name ?? "",
    category: item.category ?? "",
    price: String(priceOf(item)),
    threshold: String(thresholdOf(item)),
    barcode: item.barcode ?? "",
    description: item.description ?? "",
  };
}

/** Only the fields that changed, or an error message. */
function changesFrom(item: InventoryItem, draft: Draft): ItemFields | string {
  const name = draft.name.trim();
  if (!name) return "Name can't be empty.";
  const price = Number(draft.price || 0);
  if (!Number.isFinite(price) || price < 0) return "Price must be 0 or more.";
  const threshold = Number(draft.threshold);
  if (!Number.isInteger(threshold) || threshold < 0) return "Low-stock alert must be a whole number, 0 or more.";
  const next: ItemFields = {
    name,
    category: draft.category.trim() || "Uncategorized",
    price,
    lowStockThreshold: threshold,
    barcode: draft.barcode.trim(),
    description: draft.description.trim(),
  };
  const before: ItemFields = {
    name: item.name ?? "",
    category: item.category || "Uncategorized",
    price: priceOf(item),
    lowStockThreshold: thresholdOf(item),
    barcode: item.barcode ?? "",
    description: item.description ?? "",
  };
  return Object.fromEntries(
    (Object.keys(next) as (keyof ItemFields)[])
      .filter((key) => next[key] !== before[key])
      .map((key) => [key, next[key]]),
  ) as ItemFields;
}

export function ItemEditForm({ item }: { item: InventoryItem }) {
  const { categories } = useInventory();
  const { saveFields } = useStockActions();
  const [draft, setDraft] = useState(() => draftOf(item));
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const changes = changesFrom(item, draft);
  const dirty = typeof changes === "string" || Object.keys(changes).length > 0;

  function patch(partial: Partial<Draft>) {
    setDraft((current) => ({ ...current, ...partial }));
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (typeof changes === "string") {
      setError(changes);
      return;
    }
    if (Object.keys(changes).length === 0) return;
    setError("");
    setSaving(true);
    const saved = await saveFields(item, changes);
    setSaving(false);
    if (saved) setDraft(draftOf(saved));
  }

  return (
    <form
      aria-labelledby="details-heading"
      className="grid grid-cols-2 gap-x-3 gap-y-4"
      onSubmit={(event) => void onSubmit(event)}
      noValidate
    >
      <h3 id="details-heading" className="col-span-2 text-sm font-semibold">
        Details
      </h3>
      <Field id="e-name" label="Name" className="col-span-2">
        <Input id="e-name" value={draft.name} onChange={(event) => patch({ name: event.target.value })} />
      </Field>
      <Field id="e-category" label="Category" className="col-span-2">
        <Input
          id="e-category"
          list="item-sheet-categories"
          autoComplete="off"
          value={draft.category}
          placeholder="Uncategorized"
          onChange={(event) => patch({ category: event.target.value })}
        />
        <datalist id="item-sheet-categories">
          {categories.map((category) => (
            <option key={category} value={category} />
          ))}
        </datalist>
      </Field>
      <Field id="e-price" label={`Unit price (${currencySymbol()})`} className="col-span-1">
        <Input
          id="e-price"
          type="number"
          min={0}
          step="0.01"
          inputMode="decimal"
          className="tabular-nums"
          value={draft.price}
          onChange={(event) => patch({ price: event.target.value })}
        />
      </Field>
      <Field id="e-threshold" label="Low-stock alert at" className="col-span-1">
        <Input
          id="e-threshold"
          type="number"
          min={0}
          step={1}
          inputMode="numeric"
          className="tabular-nums"
          value={draft.threshold}
          onChange={(event) => patch({ threshold: event.target.value })}
        />
      </Field>
      <Field id="e-barcode" label="Barcode" className="col-span-2">
        <Input
          id="e-barcode"
          autoComplete="off"
          inputMode="numeric"
          value={draft.barcode}
          onChange={(event) => patch({ barcode: event.target.value })}
        />
      </Field>
      <Field id="e-description" label="Size / description" className="col-span-2">
        <textarea
          id="e-description"
          className={TEXTAREA_CLASS}
          placeholder="e.g. 150g"
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
        <Button type="submit" disabled={!dirty || saving}>
          {saving ? "Saving…" : "Save changes"}
        </Button>
        {dirty ? (
          <Button type="button" variant="ghost" onClick={() => setDraft(draftOf(item))}>
            Discard
          </Button>
        ) : null}
      </div>
    </form>
  );
}
