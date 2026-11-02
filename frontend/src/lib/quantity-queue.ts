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

/** Saves one merged batch of taps; false means it failed (the caller already rolled back and said so). */
export type SaveBatch = (delta: number) => Promise<boolean>;

type Batch = { delta: number; key: string; save: SaveBatch; timer?: ReturnType<typeof setTimeout> };

/**
 * Quantity taps per item: taps with the same `key` (reason) merge into one save `delayMs` after the
 * last tap; saves for one item run one at a time. A failed save or `cancel` drops every tap for that
 * item that has not been sent yet. `onChange(id)` fires whenever `isPending(id)` may have changed.
 */
export function createQuantityQueue(onChange: (id: string) => void, delayMs = 1000) {
  const open = new Map<string, Batch>();
  const writes = new Map<string, Promise<unknown>>();
  // Taps not sent yet (open batch + flushed batches waiting behind the in-flight save).
  const unsent = new Map<string, number>();
  const epochs = new Map<string, number>();
  // Bumped on every tap or replace, so a reload can tell which rows changed after it started.
  let touches = 0;
  const touchedAt = new Map<string, number>();

  function addUnsent(id: string, by: number) {
    const total = (unsent.get(id) ?? 0) + by;
    if (total) unsent.set(id, total);
    else unsent.delete(id);
  }

  function run(id: string, task: () => Promise<unknown>): Promise<unknown> {
    const write = serialize(writes, id, () => task().catch(() => false));
    void write.then(() => onChange(id));
    return write;
  }

  function drop(id: string) {
    clearTimeout(open.get(id)?.timer);
    open.delete(id);
    unsent.delete(id);
    epochs.set(id, (epochs.get(id) ?? 0) + 1);
  }

  function cancel(id: string) {
    drop(id);
    onChange(id);
  }

  /** Drops unsent taps and queues `task` in one step, so `id` never reads as not pending in between. */
  function replace(id: string, task: () => Promise<unknown>): Promise<unknown> {
    drop(id);
    touchedAt.set(id, ++touches);
    const write = run(id, task);
    onChange(id);
    return write;
  }

  function flush(id: string) {
    const batch = open.get(id);
    if (!batch) return;
    clearTimeout(batch.timer);
    open.delete(id);
    const epoch = epochs.get(id) ?? 0;
    void run(id, async () => {
      if ((epochs.get(id) ?? 0) !== epoch) return; // cancelled while waiting its turn
      addUnsent(id, -batch.delta);
      if (!(await batch.save(batch.delta))) cancel(id);
    });
  }

  function tap(id: string, delta: number, key: string, save: SaveBatch) {
    if (open.get(id)?.key !== key) flush(id);
    const batch = open.get(id) ?? { delta: 0, key, save };
    clearTimeout(batch.timer);
    batch.delta += delta;
    batch.save = save;
    batch.timer = setTimeout(() => flush(id), delayMs);
    open.set(id, batch);
    addUnsent(id, delta);
    touchedAt.set(id, ++touches);
    onChange(id);
  }

  return {
    tap,
    flush,
    cancel,
    replace,
    run,
    flushAll: () => [...open.keys()].forEach(flush),
    cancelAll: () => [...new Set([...open.keys(), ...writes.keys()])].forEach(cancel),
    /** Taps for `id` not sent to the server yet; the cache shows server row + this. */
    unsent: (id: string) => unsent.get(id) ?? 0,
    isPending: (id: string) => open.has(id) || writes.has(id),
    /** Pass to `tappedSince` later: true when `id` was tapped or replaced after this mark. */
    mark: () => touches,
    tappedSince: (id: string, mark: number) => (touchedAt.get(id) ?? 0) > mark,
  };
}

export type QuantityQueue = ReturnType<typeof createQuantityQueue>;
