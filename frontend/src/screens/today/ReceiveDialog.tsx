import { useState, type FormEvent } from "react";
import { useInventory } from "@/app/inventory-store";
import { useStockActions } from "@/app/use-stock-actions";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { quantityOf } from "@/lib/dashboardStats";

type ReceiveDialogProps = {
  itemID: string | null;
  onClose: () => void;
};

/**
 * Quick "a delivery arrived" from Today: adds units with a "Received N" note.
 */
export function ReceiveDialog({ itemID, onClose }: ReceiveDialogProps) {
  const { items } = useInventory();
  const { setQuantityOptimistic } = useStockActions();
  const item = itemID ? (items.find((entry) => entry.itemID === itemID) ?? null) : null;
  const [amount, setAmount] = useState("");
  const [error, setError] = useState("");

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!item) return;
    const units = Number(amount);
    if (!Number.isInteger(units) || units < 1) {
      setError("Enter how many arrived (a whole number, 1 or more).");
      return;
    }
    // Shows on Today at once; the store saves it (and says so if the save fails).
    setQuantityOptimistic(item, units, "Received");
    setAmount("");
    setError("");
    onClose();
  }

  return (
    <Dialog
      open={item !== null}
      onOpenChange={(open) => {
        if (!open) {
          setAmount("");
          setError("");
          onClose();
        }
      }}
    >
      <DialogContent>
        <form className="grid gap-6" onSubmit={onSubmit} noValidate>
          <DialogHeader>
            <DialogTitle>Receive {item?.name || "item"}</DialogTitle>
            <DialogDescription>
              {item ? `${quantityOf(item)} on hand now. Enter what arrived.` : ""}
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="receive-amount">Units received</Label>
            <Input
              id="receive-amount"
              type="number"
              min={1}
              step={1}
              inputMode="numeric"
              autoFocus
              className="text-lg font-semibold tabular-nums"
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
            />
            {error ? (
              <p role="alert" className="text-sm text-destructive">
                {error}
              </p>
            ) : null}
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit">
              Add to stock
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
