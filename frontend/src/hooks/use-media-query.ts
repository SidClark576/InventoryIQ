import { useSyncExternalStore } from "react";

export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (onChange) => {
      const list = window.matchMedia(query);
      list.addEventListener("change", onChange);
      return () => list.removeEventListener("change", onChange);
    },
    () => window.matchMedia(query).matches,
    () => false,
  );
}

/** Matches Tailwind's `md` breakpoint: sidebar and side sheets from 768px up. */
export function useIsDesktop(): boolean {
  return useMediaQuery("(min-width: 768px)");
}
