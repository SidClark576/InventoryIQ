/** Never step below zero: the most a − can take away is what is on the shelf. */
export function clampDelta(current: number, delta: number): number {
  return Math.max(delta, 0 - Math.max(current, 0)); // 0 - x, not -x: no -0
}

/** The write a batch of −/+ taps turns into, or null when nothing changes. */
export function settleStep(current: number, delta: number): { next: number; notes: string } | null {
  const next = Math.max(0, current + delta);
  if (next === current) return null;
  const n = Math.abs(next - current);
  return { next, notes: next < current ? `Sold ${n}` : `Received ${n}` };
}

/**
 * Runs writes for one key one after another. Each write gets the previous write's result: the store
 * only refreshes on the next render, so reading it right after a save would send a stale version.
 */
export function serialize<T>(
  queue: Map<string, Promise<T>>,
  key: string,
  run: (previous: T | undefined) => Promise<T>,
): Promise<T> {
  const previous: Promise<T | undefined> = queue.get(key) ?? Promise.resolve(undefined);
  const write = previous.then(run);
  queue.set(key, write);
  const forget = () => {
    if (queue.get(key) === write) queue.delete(key);
  };
  write.then(forget, forget);
  return write;
}
