import { useEffect, useLayoutEffect, useState } from "react";
import { flushSync } from "react-dom";
import { inCurrentOrg, type OrgScoped } from "@/lib/org-shell";
import type { StockReport } from "./ReportDialog";

/**
 * The report being previewed and the one printing. The preview is its own state: afterprint clears the printing
 * report and must not close a preview the user is still reading. An org switch closes the preview (old org's stock).
 */
export function usePrintReport(orgEpoch: number) {
  const [report, setReport] = useState<StockReport | null>(null);
  const [opened, setOpened] = useState<OrgScoped<StockReport> | null>(null);
  const preview = inCurrentOrg(opened, orgEpoch);
  const setPreview = (next: StockReport | null) => setOpened(next && { value: next, orgEpoch });
  const printable = report ?? preview;

  // Print styles key off this attribute (index.css). It is set while a report prints or is previewed, so Ctrl+P with
  // the preview open prints the report. After printing, the report drops so a later Ctrl+P prints the page as is.
  useLayoutEffect(() => {
    if (!printable) return;
    document.documentElement.dataset.iqPrint = "inventory";
    return () => {
      delete document.documentElement.dataset.iqPrint;
    };
  }, [printable]);

  useEffect(() => {
    const clear = () => setReport(null);
    window.addEventListener("afterprint", clear);
    return () => window.removeEventListener("afterprint", clear);
  }, []);

  function print(next: StockReport) {
    // flushSync renders the report (and closes the preview, which iOS needs) before the browser snapshots the page.
    flushSync(() => {
      setReport(next);
      setPreview(null);
    });
    window.print();
  }

  return { printable, preview, setPreview, print };
}
