import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

type PageHeaderProps = {
  title: ReactNode;
  description?: ReactNode;
  /** Buttons or links shown at the right on wide screens, below the title on narrow ones. */
  actions?: ReactNode;
  titleId?: string;
  className?: string;
};

export function PageHeader({ title, description, actions, titleId, className }: PageHeaderProps) {
  return (
    <header className={cn("flex flex-wrap items-end justify-between gap-x-6 gap-y-3", className)}>
      <div className="min-w-0">
        <h1
          id={titleId}
          className="font-heading text-2xl font-semibold tracking-tight text-balance"
        >
          {title}
        </h1>
        {description ? (
          <p className="mt-1 text-sm text-pretty text-muted-foreground">{description}</p>
        ) : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </header>
  );
}
