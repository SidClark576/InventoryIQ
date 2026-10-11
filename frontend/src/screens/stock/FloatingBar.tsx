import type { ReactNode } from "react";

/** Action bar pinned above the bottom tab bar (mobile) or the page bottom (desktop). */
export function FloatingBar({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div
      role="region"
      aria-label={label}
      className="fixed inset-x-3 bottom-[calc(4.75rem+env(safe-area-inset-bottom))] z-40 mx-auto flex max-w-2xl items-center gap-2 rounded-3xl border border-border bg-popover/95 p-2 pl-4 text-popover-foreground shadow-2xl ring-1 ring-foreground/5 backdrop-blur-md animate-in fade-in-0 slide-in-from-bottom-4 md:bottom-6 md:left-[calc(15rem+1.5rem)] md:right-6"
    >
      {children}
    </div>
  );
}
