export type BarMetric = "tokens_per_s" | "lines_per_hour" | "s_per_chunk";
export const BAR_METRICS: BarMetric[] = ["tokens_per_s", "lines_per_hour", "s_per_chunk"];

/** Bar heights as a percentage of the tallest value; a missing or non-positive value is 0. */
export function barHeights(values: (number | null | undefined)[]): number[] {
  const max = values.reduce<number>((m, v) => (v != null && v > m ? v : m), 0);
  return values.map((v) => (v != null && v > 0 && max > 0 ? (v / max) * 100 : 0));
}

/** Whole-number shares of used / edited / ignored, or null when there are no outcomes yet. */
export function outcomePcts(o: { used: number; edited: number; ignored: number }) {
  const total = o.used + o.edited + o.ignored;
  if (total === 0) return null;
  const pct = (v: number) => Math.round((v / total) * 100);
  return { used: pct(o.used), edited: pct(o.edited), ignored: pct(o.ignored) };
}
