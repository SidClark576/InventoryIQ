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
import { reasonNote } from "@/lib/reasons";

type ReceiveDialogProps = {
  itemID: string | null;
  onClose: () => void;
};

/**
 * Quick "a delivery arrived" from Today: adds units with a "Received N" note.
 * Reads the item from the store on every render so a retry after a 412 uses the fresh version.
 */
export function ReceiveDialog({ itemID, onClose }: ReceiveDialogProps) {
  const { items } = useInventory();
  const { setQuantity } = useStockActions();
  const item = itemID ? (items.find((entry) => entry.itemID === itemID) ?? null) : null;
  const [amount, setAmount] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!item) return;
    const units = Number(amount);
    if (!Number.isInteger(units) || units < 1) {
      setError("Enter how many arrived (a whole number, 1 or more).");
      return;
    }
    setBusy(true);
    const saved = await setQuantity(item, quantityOf(item) + units, reasonNote("Received", "add", units));
    setBusy(false);
    if (saved) {
      setAmount("");
      setError("");
      onClose();
    }
  }

  return (
    <Dialog
      open={item !== null}
      onOpenChange={(open) => {
        if (!open && !busy) {
          setAmount("");
          setError("");
          onClose();
        }
      }}
    >
      <DialogContent>
        <form className="grid gap-6" onSubmit={(event) => void onSubmit(event)} noValidate>
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
            <Button type="button" variant="outline" disabled={busy} onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={busy}>
              {busy ? "Saving…" : "Add to stock"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
