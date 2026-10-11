/** User-facing message for a caught value: the Error's message, else `fallback`. */
export function errorText(err: unknown, fallback = ""): string {
  return err instanceof Error && err.message ? err.message : fallback;
}
