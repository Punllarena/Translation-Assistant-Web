/** Tick or untick `id`; with shift and an anchor still in `order`, every id between the
 *  anchor and `id` (either direction) takes `id`'s new state. Returns a new set. */
export function rangeToggle(order: number[], picked: Set<number>, id: number, anchor: number | null, shift: boolean): Set<number> {
  const next = new Set(picked);
  const on = !picked.has(id);
  const from = anchor === null ? -1 : order.indexOf(anchor);
  const to = order.indexOf(id);
  const ids = shift && from >= 0 && to >= 0
    ? order.slice(Math.min(from, to), Math.max(from, to) + 1)
    : [id];
  for (const v of ids) { if (on) next.add(v); else next.delete(v); }
  return next;
}
