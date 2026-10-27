import { useState, type FormEvent } from "react";
import type { InventoryItem } from "@/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { quantityOf } from "@/lib/dashboardStats";
import { countedValue, nextUncounted, type Counts } from "./count";
import type { StockGroup } from "./stock-view";
import { Variance } from "./StockTable";

type CountCardsProps = {
  /** Current Stock grouping, so cards follow the shelf order. */
  groups: readonly StockGroup[];
  counts: Counts;
  onCount: (itemID: string, value: string) => void;
  /** Next pressed and nothing is left uncounted. */
  onReview: () => void;
};

/** Brings each new card (keyed per item) fully into view above the fixed count bar; module-level so it runs on mount only. */
function reveal(form: HTMLFormElement | null) {
  form?.scrollIntoView({ block: "nearest" });
}

/** Phone count mode: one item per card, auto-advancing to the next uncounted item. */
export function CountCards({ groups, counts, onCount, onReview }: CountCardsProps) {
  const [index, setIndex] = useState(0);
  const cards = groups.flatMap((group) => group.items.map((item) => ({ item, group: group.title })));
  const items: InventoryItem[] = cards.map((card) => card.item);
  const at = Math.min(index, cards.length - 1);
  const card = cards[at];
  if (!card) return null;

  const { item, group } = card;
  const id = item.itemID ?? "";
  const name = item.name || "Untitled item";
  const expected = quantityOf(item);
  const raw = counts[id] ?? "";
  const value = countedValue(raw);
  const invalid = raw.trim() !== "" && value === null;

  function advance() {
    const to = nextUncounted(items, counts, at);
    if (to === null) onReview();
    else setIndex(to);
  }

  function next(event: FormEvent) {
    event.preventDefault();
    if (!invalid) advance();
  }

  function skip() {
    onCount(id, "");
    advance();
  }

  return (
    <form
      key={id}
      ref={reveal}
      onSubmit={next}
      aria-label="Count item"
      className="flex scroll-mt-20 scroll-mb-44 flex-col gap-4 rounded-3xl border border-border bg-card p-5 text-card-foreground"
    >
      <p className="text-sm text-muted-foreground tabular-nums">
        {at + 1} of {cards.length} · {group}
      </p>
      <div className="flex flex-col gap-1">
        <h2 className="font-heading text-2xl leading-tight font-semibold break-words">{name}</h2>
        <p className="text-sm break-words text-muted-foreground">
          {[item.category || "Uncategorized", item.description].filter(Boolean).join(" · ")}
        </p>
      </div>
      <p className="text-base">
        Expected <span className="font-semibold tabular-nums">{expected}</span>
      </p>
      <div className="flex items-center gap-2">
        <Input
          type="number"
          min={0}
          step={1}
          inputMode="numeric"
          enterKeyHint="next"
          autoFocus
          aria-label={`Counted ${name}`}
          aria-invalid={invalid || undefined}
          value={raw}
          onChange={(event) => onCount(id, event.target.value)}
          className="h-14 flex-1 text-2xl tabular-nums md:text-2xl"
        />
        <Button type="button" variant="outline" className="h-14 px-5" onClick={() => onCount(id, String(expected))}>
          Same
        </Button>
      </div>
      <p className="min-h-6 text-lg" aria-live="polite">
        {value !== null ? <Variance expected={expected} counted={value} /> : invalid ? (
          <span className="text-sm text-destructive">Enter a whole number, 0 or more.</span>
        ) : null}
      </p>
      <div className="grid grid-cols-3 gap-2">
        <Button type="button" variant="outline" className="h-11" disabled={at === 0} onClick={() => setIndex(at - 1)}>
          Back
        </Button>
        <Button type="button" variant="ghost" className="h-11" onClick={skip}>
          Skip
        </Button>
        <Button type="submit" className="h-11" disabled={invalid}>
          Next
        </Button>
      </div>
    </form>
  );
}
