import type { Schemas } from "../api/client";
import { COLORS, intensity, thresholds, weeks, type Metric } from "./heatmapGrid";

const CELL = 13, STEP = 15, LEFT = 30, TOP = 16;
const UNITS: Record<Metric, string> = { paragraphs: "paras", chars: "chars", en_words: "EN words" };
const longDate = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { dateStyle: "long" });

/** The 52-week activity grid; the per-day table below the page carries the same data for screen readers. */
export default function Heatmap({ today, daily, metric, onPick }: {
  today: string; daily: Schemas["DayStats"][]; metric: Metric; onPick: (iso: string) => void;
}) {
  const byDate = new Map(daily.map((d) => [d.date, d]));
  const th = thresholds(daily.map((d) => d[metric]));
  const grid = weeks(today);
  const months = grid.map((col, i) => (i > 0 && col[0]!.slice(5, 7) !== grid[i - 1][0]!.slice(5, 7)
    ? new Date(`${col[0]}T00:00:00`).toLocaleDateString(undefined, { month: "short" }) : ""));
  return (
    <svg role="img" aria-label={`Activity heatmap of ${UNITS[metric]} over the last 52 weeks`}
      width={LEFT + 52 * STEP} height={TOP + 7 * STEP} style={{ maxWidth: "100%" }}>
      {[[1, "Mon"], [3, "Wed"], [5, "Fri"]].map(([row, name]) => (
        <text key={name} x={LEFT - 4} y={TOP + (row as number) * STEP + 10} textAnchor="end" fontSize="9" fill="#767676">{name}</text>
      ))}
      {months.map((m, i) => m && <text key={i} x={LEFT + i * STEP} y={TOP - 4} fontSize="9" fill="#767676">{m}</text>)}
      {grid.flatMap((col, c) => col.map((iso, r) => {
        if (!iso) return null;
        const d = byDate.get(iso);
        const tip = `${longDate(iso)}: ${d?.paragraphs ?? 0} paras · ${d?.chars ?? 0} chars · ${d?.en_words ?? 0} EN words`;
        return (
          <rect key={iso} x={LEFT + c * STEP} y={TOP + r * STEP} width={CELL} height={CELL}
            fill={COLORS[intensity(d?.[metric] ?? 0, th)]} onClick={() => onPick(iso)} style={{ cursor: "pointer" }}>
            <title>{tip}</title>
          </rect>
        );
      }))}
    </svg>
  );
}
