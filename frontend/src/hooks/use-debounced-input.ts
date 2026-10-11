import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Local text for a search box whose committed value (e.g. `?q=`) follows `delay` ms after typing stops,
 * so each keystroke does not rewrite the URL and refilter the list.
 * Outside changes to `value` (Clear filters, Back) replace the local text.
 */
export function useDebouncedInput(
  value: string,
  commit: (next: string) => void,
  delay = 250,
): [string, (next: string) => void] {
  const [local, setLocal] = useState(value);
  const committed = useRef(value);
  const timer = useRef<number | undefined>(undefined);
  const commitRef = useRef(commit);

  useEffect(() => {
    commitRef.current = commit;
  });

  useEffect(() => {
    if (value === committed.current) return;
    window.clearTimeout(timer.current);
    committed.current = value;
    setLocal(value);
  }, [value]);

  useEffect(() => () => window.clearTimeout(timer.current), []);

  const change = useCallback(
    (next: string) => {
      setLocal(next);
      window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => {
        committed.current = next;
        commitRef.current(next);
      }, delay);
    },
    [delay],
  );

  return [local, change];
}
