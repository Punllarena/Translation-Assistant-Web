export const METRICS = ["paragraphs", "chars", "en_words"] as const;
export type Metric = (typeof METRICS)[number];
/** Intensity levels; each is painted by the .heat-N classes in styles/stats.css (tokens --h0…--h4). */
export const LEVELS = [0, 1, 2, 3, 4] as const;

/** 52 week columns of 7 ISO dates (Sunday first) ending with the week of `today`; null after today. */
export function weeks(today: string): (string | null)[][] {
  const t = new Date(`${today}T00:00:00Z`);
  const start = new Date(t);
  start.setUTCDate(t.getUTCDate() - t.getUTCDay() - 51 * 7);
  return Array.from({ length: 52 }, (_, col) => Array.from({ length: 7 }, (_, row) => {
    const d = new Date(start);
    d.setUTCDate(start.getUTCDate() + col * 7 + row);
    const iso = d.toISOString().slice(0, 10);
    return iso > today ? null : iso;
  }));
}

/** The desktop's level boundaries: quarters of the all-time max. */
export function thresholds(values: number[]): number[] {
  const max = values.reduce((a, b) => Math.max(a, b), 0);
  if (max <= 0) return [0, 1, 2, 3, 4];
  const q = max / 4;
  return [0, q, 2 * q, 3 * q, max];
}

export function intensity(value: number, th: number[]): number {
  if (value === 0) return 0;
  for (let level = 4; level > 0; level--) if (value >= th[level]) return level;
  return 1;
}
