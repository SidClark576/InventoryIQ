import { useState } from "react";
import { MinusIcon, PlusIcon } from "@phosphor-icons/react";
import type { InventoryItem } from "@/api";
import { useStockActions } from "@/app/use-stock-actions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { quantityOf } from "@/lib/dashboardStats";
import { nextQuantity, reasonAllows, reasonNote, REASONS, type Direction, type Reason } from "@/lib/reasons";

type AdjustControlsProps = {
  item: InventoryItem;
  /** Pre-selects a reason, e.g. "Received" from Today's Receive action. */
  initialReason?: Reason | null;
};

export function AdjustControls({ item, initialReason = null }: AdjustControlsProps) {
  const { setQuantity } = useStockActions();
  const [amount, setAmount] = useState("1");
  const [reason, setReason] = useState<Reason | null>(initialReason);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const current = quantityOf(item);

  async function apply(direction: Direction) {
    const units = Number(amount);
    if (!Number.isInteger(units) || units < 1) {
      setError("Enter a whole number of 1 or more.");
      return;
    }
    if (direction === "remove" && units > current) {
      setError(`Only ${current} on hand.`);
      return;
    }
    setError("");
    setBusy(true);
    const saved = await setQuantity(
      item,
      nextQuantity(current, direction, units),
      reasonNote(reason, direction, units),
    );
    setBusy(false);
    if (saved) {
      setReason(null);
      setAmount("1");
    }
  }

  return (
    <section aria-labelledby="adjust-heading" className="flex flex-col gap-3">
      <h3 id="adjust-heading" className="text-sm font-semibold">
        Adjust stock
      </h3>
      <div className="flex items-center gap-2">
        <Button
          type="button"
          variant="outline"
          size="lg"
          className="flex-1"
          disabled={busy || current <= 0 || !reasonAllows(reason, "remove")}
          onClick={() => void apply("remove")}
        >
          <MinusIcon />
          Remove
        </Button>
        <Input
          id="adjust-amount"
          type="number"
          min={1}
          step={1}
          inputMode="numeric"
          aria-label="Amount"
          value={amount}
          onChange={(event) => setAmount(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              void apply(reason === "Received" ? "add" : "remove");
            }
          }}
          className="h-10 w-20 text-center text-base font-semibold tabular-nums"
        />
        <Button
          type="button"
          size="lg"
          className="flex-1"
          disabled={busy || !reasonAllows(reason, "add")}
          onClick={() => void apply("add")}
        >
          <PlusIcon />
          Add
        </Button>
      </div>
      <div className="flex flex-col gap-1.5">
        <span id="reason-label" className="text-xs text-muted-foreground">
          Reason (optional, saved with the change)
        </span>
        <ToggleGroup
          aria-labelledby="reason-label"
          value={reason ? [reason] : []}
          onValueChange={(value) => setReason((value[0] as Reason | undefined) ?? null)}
          variant="outline"
          size="sm"
          spacing={1}
          className="flex-wrap"
        >
          {REASONS.map((option) => (
            <ToggleGroupItem
              key={option}
              value={option}
              className="aria-pressed:border-primary/50 aria-pressed:bg-primary/12 aria-pressed:text-foreground"
            >
              {option}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      </div>
      <p className="min-h-4 text-xs text-destructive" role="alert">
        {error}
      </p>
    </section>
  );
}
