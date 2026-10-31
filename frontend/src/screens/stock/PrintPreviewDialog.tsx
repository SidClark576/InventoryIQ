import { PrinterIcon } from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { ReportTable } from "./PrintReport";
import type { StockReport } from "./ReportDialog";

type PrintPreviewDialogProps = {
  /** Open while set. A snapshot: printing prints this, even if stock changes meanwhile. */
  report: StockReport | null;
  storeName: string;
  onBack: () => void;
  onPrint: (report: StockReport) => void;
};

const time = (date: Date) => date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });

/** Shows the paper sheet before printing: wide on desktop, full screen on phones. */
export function PrintPreviewDialog({ report, storeName, onBack, onPrint }: PrintPreviewDialogProps) {
  return (
    <Dialog open={report !== null} onOpenChange={(open) => (open ? undefined : onBack())}>
      <DialogContent
        showCloseButton={false}
        className="flex h-dvh max-h-dvh w-full max-w-none flex-col gap-0 rounded-none p-0 sm:h-[90dvh] sm:max-w-4xl sm:rounded-4xl"
      >
        {report ? (
          <>
            <DialogHeader className="border-b border-border p-4 sm:p-6">
              <DialogTitle>{report.selected ? "Selected items" : "Stock report"}</DialogTitle>
              <DialogDescription>As of {time(report.asOf)}. This is what prints.</DialogDescription>
            </DialogHeader>
            <div className="min-h-0 flex-1 overflow-y-auto bg-muted p-3 sm:p-6">
              {/* White paper on purpose, in dark theme too. Wide tables scroll inside the paper only. */}
              <div className="report-sheet mx-auto max-w-[210mm] overflow-x-auto rounded-lg border border-border p-4 shadow-sm sm:p-8 [&_table]:min-w-[640px]">
                <ReportTable report={report} storeName={storeName} />
              </div>
            </div>
            <DialogFooter className="border-t border-border p-4 pb-[max(1rem,env(safe-area-inset-bottom))] sm:px-6">
              <Button type="button" variant="outline" className="h-11" onClick={onBack}>
                Back
              </Button>
              <Button type="button" className="h-11" onClick={() => onPrint(report)}>
                <PrinterIcon />
                Print or save PDF
              </Button>
            </DialogFooter>
          </>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
