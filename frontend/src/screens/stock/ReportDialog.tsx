import { useState } from "react";
import { toast } from "sonner";
import { getTransactions, type InventoryItem } from "@/api";
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
import { parseTransactions } from "@/lib/activity";
import { errorText } from "@/lib/errors";
import { plural } from "@/lib/format";
import { buildStockReport, defaultStartDate, localDate, type ReportGroup } from "@/lib/stock-report";
import { downloadReportCsv } from "./export";

export type StockReport = { groups: ReportGroup[]; start: Date; asOf: Date; selected: boolean };

type ReportDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  items: readonly InventoryItem[];
  /** The items are a selection, not the whole store: says so and names the CSV `_selected`. */
  selected: boolean;
  onPrint: (report: StockReport) => void;
  /** Coming Back from the print preview: the form keeps the previewed start date (YYYY-MM-DD) and focus returns to Print. */
  backStart?: string;
};

/** One dialog for both report outputs: pick the start date, then Export CSV or Print. */
export function ReportDialog({ open, onOpenChange, items, selected, onPrint, backStart }: ReportDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm" initialFocus={backStart ? () => document.getElementById("report-print") : true}>
        {/* Mounted only while open, so the date and error reset each time (Back from the preview keeps the date). */}
        <ReportForm items={items} selected={selected} onDone={() => onOpenChange(false)} onPrint={onPrint} backStart={backStart} />
      </DialogContent>
    </Dialog>
  );
}

function ReportForm({ items, selected, onDone, onPrint, backStart }: Omit<ReportDialogProps, "open" | "onOpenChange"> & { onDone: () => void }) {
  const today = localDate(new Date());
  const [date, setDate] = useState(() => backStart ?? defaultStartDate());
  const [busy, setBusy] = useState<"csv" | "print" | null>(null);
  const [error, setError] = useState("");

  async function run(kind: "csv" | "print") {
    const start = new Date(`${date}T00:00:00`);
    if (!date || date > today || Number.isNaN(start.getTime())) {
      setError("Pick a start date on or before today.");
      return;
    }
    setBusy(kind);
    setError("");
    try {
      const txs = parseTransactions(await getTransactions(start.toISOString()));
      const report = { groups: buildStockReport(items, txs, start), start, asOf: new Date(), selected };
      onDone();
      if (kind === "print") {
        onPrint(report);
        return;
      }
      downloadReportCsv(report.groups, report.asOf, selected ? "_selected" : "");
      toast.success(`Exported ${plural(items.length, "item")}`);
    } catch (err: unknown) {
      setError(errorText(err, "Couldn't load stock history. Try again."));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="grid gap-6">
      <DialogHeader>
        <DialogTitle>{selected ? "Selected items" : "Stock report"}</DialogTitle>
        <DialogDescription>
          {selected ? `Report for ${plural(items.length, "selected item")}.` : `Report for all ${plural(items.length, "item")}.`} Starting stock is what you had on this date. Stock in counts deliveries since then.
        </DialogDescription>
      </DialogHeader>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="report-start">Start date</Label>
        <Input id="report-start" type="date" max={today} value={date} onChange={(event) => setDate(event.target.value)} />
        {error ? (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        ) : null}
      </div>
      <DialogFooter>
        <Button id="report-csv" type="button" variant="outline" disabled={busy !== null} onClick={() => void run("csv")}>
          {busy === "csv" ? "Exporting…" : "Export CSV"}
        </Button>
        <Button id="report-print" type="button" disabled={busy !== null || items.length === 0} onClick={() => void run("print")}>
          {items.length === 0 ? "Nothing to print yet" : busy === "print" ? "Loading…" : "Print"}
        </Button>
      </DialogFooter>
    </div>
  );
}
