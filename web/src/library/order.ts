/** A copy of `items` with the element at `from` moved to index `to`. */
export function moveItem<T>(items: T[], from: number, to: number): T[] {
  const next = [...items];
  const [moved] = next.splice(from, 1);
  next.splice(to, 0, moved);
  return next;
}

/** The index `delta` places away from `index`, or null when that falls outside `0..length-1`. */
export function shiftIndex(index: number, delta: -1 | 1, length: number): number | null {
  if (index < 0 || index >= length) return null;
  const next = index + delta;
  return next >= 0 && next < length ? next : null;
}
