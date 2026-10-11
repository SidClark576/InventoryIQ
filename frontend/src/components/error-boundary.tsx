import { Component, type ReactNode } from "react";
import { Button } from "@/components/ui/button";

type ErrorBoundaryProps = { children: ReactNode };
type ErrorBoundaryState = { failed: boolean };

/**
 * Catches render errors and failed lazy chunk loads (e.g. after a deploy) and offers a reload.
 * React already reports caught errors to the console, so there is no componentDidCatch.
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { failed: false };

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { failed: true };
  }

  render(): ReactNode {
    if (!this.state.failed) return this.props.children;
    return (
      <div role="alert" className="flex min-h-svh flex-col items-center justify-center gap-4 bg-background p-6 text-center text-foreground">
        <h1 className="font-heading text-2xl font-semibold">Something went wrong</h1>
        <p className="max-w-sm text-sm text-muted-foreground">
          This page failed to load. Reloading usually fixes it, especially right after an update.
        </p>
        <Button type="button" onClick={() => window.location.reload()}>
          Reload
        </Button>
      </div>
    );
  }
}
