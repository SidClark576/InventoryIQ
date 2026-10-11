import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type BarcodeHit = { codeResult?: { code?: string } };

type QuaggaConfig = {
  inputStream?: { type: string; target: HTMLElement; constraints: { facingMode: string } };
  decoder: { readers: string[] };
  locate: boolean;
  src?: string;
};

type QuaggaLib = {
  init(config: QuaggaConfig, callback: (err: unknown) => void): void;
  start(): void;
  stop(): void;
  onDetected(callback: (result: BarcodeHit) => void): void;
  decodeSingle(config: QuaggaConfig, callback: (result: BarcodeHit | undefined) => void): void;
};

const READERS = ["ean_reader", "upc_reader", "code_128_reader"];
// Pinned: the CSP allows cdn.jsdelivr.net for this script only.
const QUAGGA_SRC = "https://cdn.jsdelivr.net/npm/@ericblade/quagga2@1.12.1/dist/quagga.min.js";

let quaggaLoad: Promise<void> | null = null;

function getQuagga(): QuaggaLib | undefined {
  return (window as Window & { Quagga?: QuaggaLib }).Quagga;
}

function loadQuagga(): Promise<void> {
  if (getQuagga()) return Promise.resolve();
  if (quaggaLoad) return quaggaLoad;
  quaggaLoad = new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = QUAGGA_SRC;
    script.onload = () => resolve();
    script.onerror = () => {
      quaggaLoad = null;
      reject(new Error("Failed to load the barcode scanner"));
    };
    document.head.appendChild(script);
  });
  return quaggaLoad;
}

type BarcodeScanDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  description: string;
  /** Handles a scanned or typed code. Return a message to stay open and show it; return nothing when done. */
  onCode: (code: string) => Promise<string | void>;
};

export function BarcodeScanDialog({ open, onOpenChange, description, onCode }: BarcodeScanDialogProps) {
  const [fallback, setFallback] = useState(false);
  const [status, setStatus] = useState("");
  const [manualCode, setManualCode] = useState("");
  const targetRef = useRef<HTMLDivElement>(null);
  const running = useRef(false);
  const busy = useRef(false);
  const onCodeRef = useRef(onCode);
  onCodeRef.current = onCode;

  function stopCamera() {
    if (!running.current) return;
    try {
      getQuagga()?.stop();
    } catch {
      // Already stopped.
    }
    running.current = false;
  }

  async function handleCode(code: string) {
    if (busy.current) return;
    busy.current = true;
    stopCamera();
    setStatus(`Found ${code}. Looking it up…`);
    try {
      const message = await onCodeRef.current(code);
      if (message) {
        setStatus(message);
        setFallback(true);
      }
    } catch (err: unknown) {
      setStatus(err instanceof Error ? err.message : "Lookup failed");
      setFallback(true);
    } finally {
      busy.current = false;
    }
  }

  useEffect(() => {
    if (!open) return;
    let alive = true;
    busy.current = false;
    setFallback(false);
    setManualCode("");
    setStatus("Starting camera…");
    void loadQuagga()
      .then(() => {
        const quagga = getQuagga();
        const target = targetRef.current;
        if (!alive) return;
        if (!quagga || !target) {
          setFallback(true);
          setStatus("");
          return;
        }
        quagga.init(
          {
            inputStream: { type: "LiveStream", target, constraints: { facingMode: "environment" } },
            decoder: { readers: READERS },
            locate: true,
          },
          (err) => {
            if (!alive) return;
            if (err) {
              setFallback(true);
              setStatus("");
              return;
            }
            quagga.start();
            running.current = true;
            setStatus("Point the camera at a barcode.");
            quagga.onDetected((result) => {
              const code = result?.codeResult?.code;
              if (alive && code) void handleCode(code);
            });
          },
        );
      })
      .catch(() => {
        if (!alive) return;
        setFallback(true);
        setStatus("");
      });
    return () => {
      alive = false;
      stopCamera();
    };
    // Restart only when the dialog opens; handleCode reads the latest onCode through a ref.
  }, [open]);

  function scanImage(file: File | undefined) {
    const quagga = getQuagga();
    if (!file || !quagga) return;
    const src = URL.createObjectURL(file);
    setStatus("Reading the image…");
    quagga.decodeSingle({ decoder: { readers: READERS }, locate: true, src }, (result) => {
      URL.revokeObjectURL(src);
      const code = result?.codeResult?.code;
      if (!code) {
        setStatus("No barcode found in that image.");
        return;
      }
      void handleCode(code);
    });
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) stopCamera();
        onOpenChange(next);
      }}
    >
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Scan barcode</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        {fallback ? (
          <form
            id="inv-scan-fallback"
            className="flex flex-col gap-3"
            onSubmit={(event) => {
              event.preventDefault();
              const code = manualCode.trim();
              if (code) void handleCode(code);
            }}
          >
            <Label htmlFor="inv-scan-manual-input">Barcode</Label>
            <div className="flex gap-2">
              <Input
                id="inv-scan-manual-input"
                value={manualCode}
                inputMode="numeric"
                autoComplete="off"
                placeholder="e.g. 737628064502"
                onChange={(event) => setManualCode(event.target.value)}
              />
              <Button type="submit">Look up</Button>
            </div>
            <Label htmlFor="inv-scan-file" className="text-xs font-normal text-muted-foreground">
              Or upload a photo of the barcode
            </Label>
            <Input
              id="inv-scan-file"
              type="file"
              accept="image/*"
              capture="environment"
              onChange={(event) => scanImage(event.target.files?.[0])}
            />
          </form>
        ) : (
          <div className="relative h-64 overflow-hidden rounded-2xl bg-black">
            <div id="inv-scan-quagga-target" ref={targetRef} className="size-full [&_video]:size-full [&_video]:object-cover" />
            <div aria-hidden className="pointer-events-none absolute inset-x-8 top-1/2 h-0.5 -translate-y-1/2 bg-destructive/80" />
          </div>
        )}
        <p id="inv-scan-status" className="min-h-5 text-center text-sm text-muted-foreground" aria-live="polite">
          {status}
        </p>
        {fallback ? null : (
          <Button type="button" variant="ghost" size="sm" className="justify-self-center" onClick={() => {
            stopCamera();
            setFallback(true);
            setStatus("");
          }}>
            Type the code instead
          </Button>
        )}
      </DialogContent>
    </Dialog>
  );
}
