/** Never step below zero: the most a − can take away is what is on the shelf. */
export function clampDelta(current: number, delta: number): number {
  return Math.max(delta, 0 - Math.max(current, 0)); // 0 - x, not -x: no -0
}
