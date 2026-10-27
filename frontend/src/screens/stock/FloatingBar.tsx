import type { ReactNode } from "react";
import { DotsThreeIcon, DownloadSimpleIcon, TrashIcon, XIcon } from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";

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

type SelectionBarProps = {
  count: number;
  canEdit: boolean;
  onExport: () => void;
  onDelete: () => void;
  onClear: () => void;
};

/** Bulk actions for selected rows. Delete sits behind "…" so a thumb can't hit it by accident. */
export function SelectionBar({ count, canEdit, onExport, onDelete, onClear }: SelectionBarProps) {
  return (
    <FloatingBar label="Selection">
      <span className="mr-auto text-sm font-medium tabular-nums">{count} selected</span>
      <Button type="button" variant="outline" size="sm" onClick={onExport}>
        <DownloadSimpleIcon />
        Export
      </Button>
      {canEdit ? (
        <DropdownMenu>
          <DropdownMenuTrigger
            render={<Button type="button" variant="outline" size="icon-sm" aria-label="More selection actions" />}
          >
            <DotsThreeIcon weight="bold" />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" side="top" className="w-44">
            <DropdownMenuItem variant="destructive" onClick={onDelete}>
              <TrashIcon />
              Delete
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      ) : null}
      <Button type="button" variant="ghost" size="icon-sm" aria-label="Clear selection" onClick={onClear}>
        <XIcon />
      </Button>
    </FloatingBar>
  );
}
