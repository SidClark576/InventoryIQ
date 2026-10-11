import { useEffect, useRef, useState } from "react";
import { DownloadSimpleIcon, UploadSimpleIcon } from "@phosphor-icons/react";
import { toast } from "sonner";
import { ApiError, bulkImport, getImportJob, uploadImportCSV } from "@/api";
import { useInventory } from "@/app/inventory-store";
import { TEXT_LINK_CLASS } from "@/components/text-link";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { parseCsv } from "@/lib/csv";
import { cn } from "@/lib/utils";

type RowError = { row?: unknown; field?: unknown; message?: unknown };

// Files up to this many rows go through POST /items/import; larger ones upload to S3 and run as a job.
const INLINE_ROW_LIMIT = 100;
const POLL_MS = 3000;

function asNumber(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function asErrors(value: unknown): RowError[] {
  return Array.isArray(value)
    ? value.filter((row): row is RowError => Boolean(row) && typeof row === "object")
    : [];
}

/** 403/404 mean the import routes are not deployed for this API stage. */
export function isUnavailable(err: unknown): boolean {
  return err instanceof ApiError && (err.status === 403 || err.status === 404);
}

type ImportDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onUnavailable: () => void;
};

export function ImportDialog({ open, onOpenChange, onUnavailable }: ImportDialogProps) {
  const { reloadItems, invalidateTransactions } = useInventory();
  const [status, setStatus] = useState("");
  const [progress, setProgress] = useState(0);
  const [errors, setErrors] = useState<RowError[]>([]);
  const [done, setDone] = useState("");
  const gen = useRef(0);
  const timer = useRef<number | null>(null);

  function cancelPolling() {
    gen.current += 1;
    if (timer.current !== null) window.clearTimeout(timer.current);
    timer.current = null;
  }

  useEffect(() => cancelPolling, []);

  useEffect(() => {
    if (!open) return;
    setStatus("");
    setProgress(0);
    setErrors([]);
    setDone("");
  }, [open]);

  function finish(inserted: number, failed: number, rowErrors: unknown) {
    setProgress(100);
    setStatus("Done");
    setErrors(asErrors(rowErrors).slice(0, 20));
    const summary = `Imported ${inserted} item${inserted === 1 ? "" : "s"}${failed ? `, ${failed} failed` : ""}.`;
    setDone(summary);
    toast.success(summary);
    void reloadItems();
    invalidateTransactions();
  }

  function fail(err: unknown) {
    setProgress(0);
    if (isUnavailable(err)) {
      setStatus("Import isn't available on this workspace yet. Add items one at a time for now.");
      onUnavailable();
      return;
    }
    setStatus(`Error: ${err instanceof Error ? err.message : "Import failed"}`);
  }

  async function poll(run: number, jobId: string, total: number): Promise<void> {
    if (run !== gen.current) return;
    try {
      const job = await getImportJob(jobId);
      if (run !== gen.current) return;
      const imported = asNumber(job.done);
      const failed = asNumber(job.failed);
      setProgress(Math.min(99, total > 0 ? Math.round(((imported + failed) / total) * 80) + 20 : 20));
      setStatus(`Processing ${imported + failed} of ${asNumber(job.total) || total}…`);
      if (job.status === "completed" || job.status === "failed") {
        finish(imported, failed, job.errors);
        return;
      }
      timer.current = window.setTimeout(() => void poll(run, jobId, total), POLL_MS);
    } catch (err: unknown) {
      if (run === gen.current) fail(err);
    }
  }

  async function handleFile(file: File | undefined) {
    if (!file) return;
    cancelPolling();
    const run = gen.current;
    setErrors([]);
    setDone("");
    const rows = parseCsv(await file.text());
    if (run !== gen.current) return;
    if (rows.length === 0) {
      setStatus("That file has no rows to import.");
      return;
    }
    try {
      if (rows.length <= INLINE_ROW_LIMIT) {
        setStatus(`Importing ${rows.length} rows…`);
        setProgress(50);
        const result = await bulkImport(rows);
        if (run === gen.current) finish(asNumber(result.inserted), asNumber(result.failed), result.errors);
        return;
      }
      setStatus("Uploading…");
      setProgress(10);
      const jobId = await uploadImportCSV(file);
      if (run !== gen.current) return;
      if (jobId === null || jobId === undefined || jobId === "") throw new Error("Import job was not created");
      setStatus("Processing in the background…");
      setProgress(20);
      await poll(run, String(jobId), rows.length);
    } catch (err: unknown) {
      if (run === gen.current) fail(err);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) cancelPolling();
        onOpenChange(next);
      }}
    >
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Import items</DialogTitle>
          <DialogDescription>
            Columns: name, category, quantity, price, lowStockThreshold, barcode. Up to {INLINE_ROW_LIMIT} rows import
            right away; bigger files run in the background.
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-4">
          <a href="/import-template.csv" download className={cn(TEXT_LINK_CLASS, "inline-flex items-center gap-2 self-start text-sm")}>
            <DownloadSimpleIcon />
            Download template
          </a>
          <label
            id="import-drop-zone"
            className="flex cursor-pointer flex-col items-center gap-2 rounded-3xl border border-dashed border-border px-6 py-8 text-center transition-colors focus-within:ring-[3px] focus-within:ring-ring/50 hover:bg-muted/40"
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => {
              event.preventDefault();
              void handleFile(event.dataTransfer.files[0]);
            }}
          >
            <UploadSimpleIcon className="size-8 text-muted-foreground" />
            <span className="text-sm text-muted-foreground">
              Drop a CSV here or <span className="font-medium text-foreground underline underline-offset-4">browse</span>
            </span>
            <input
              id="import-file-input"
              type="file"
              accept=".csv,text/csv"
              className="sr-only"
              onChange={(event) => void handleFile(event.target.files?.[0])}
            />
          </label>
          {status ? (
            <div id="import-status" className="flex flex-col gap-2" aria-live="polite">
              <span id="import-status-text" className="text-sm">
                {status}
              </span>
              <div className="h-2 overflow-hidden rounded-full bg-muted">
                <div
                  id="import-progress-bar"
                  className="h-full w-full origin-left bg-primary transition-transform"
                  style={{ transform: `scaleX(${progress / 100})` }}
                />
              </div>
            </div>
          ) : null}
          {errors.length ? (
            <div id="import-errors" className="max-h-32 overflow-y-auto text-xs text-destructive">
              {errors.map((rowError, index) => (
                <p key={`${String(rowError.row)}-${index}`}>
                  Row {String(rowError.row ?? "")} — {String(rowError.field ?? "")}: {String(rowError.message ?? "")}
                </p>
              ))}
            </div>
          ) : null}
          {done ? (
            <p id="import-success" className="text-sm font-medium text-success">
              {done}
            </p>
          ) : null}
        </div>
      </DialogContent>
    </Dialog>
  );
}
