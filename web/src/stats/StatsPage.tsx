import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, call } from "../api/client";
import { browserZone } from "../time";
import Heatmap from "./Heatmap";
import { COLORS, METRICS, type Metric } from "./heatmapGrid";

const LABELS: Record<Metric, string> = { paragraphs: "Paragraphs", chars: "Source Chars", en_words: "EN Words" };
const UNITS: Record<Metric, string> = { paragraphs: "paragraphs", chars: "source chars", en_words: "EN words" };
const n = (v: number) => v.toLocaleString();
const pct = (v: number | null | undefined) => (v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(0)}%`);
const longDate = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { dateStyle: "long" });

export default function StatsPage() {
  const queryClient = useQueryClient();
  const stats = useQuery({ queryKey: ["stats"], queryFn: () => call(api.GET("/stats", { params: { query: { tz: browserZone() } } })) });
  const settings = useQuery({ queryKey: ["settings"], queryFn: () => call(api.GET("/settings")) });
  const saveMetric = useMutation({
    mutationFn: (m: Metric) => call(api.PUT("/settings", { body: { stats_metric: m } })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["settings"] }),
  });
  const [days, setDays] = useState(30);
  const [picked, setPicked] = useState("");
  const stored = settings.data?.stats_metric;
  const metric: Metric = METRICS.includes(stored as Metric) ? (stored as Metric) : "paragraphs";
  if (stats.isPending) return <main><p className="muted">Loading…</p></main>;
  if (stats.isError) return <main><p className="error" role="alert">{stats.error.message}</p></main>;
  const s = stats.data;
  const comp = s.comparisons[metric];
  const best = s.daily.reduce<typeof s.daily[number] | null>((b, d) => (!b || d[metric] > b[metric] ? d : b), null);
  const cutoff = new Date(`${s.today}T00:00:00Z`);
  cutoff.setUTCDate(cutoff.getUTCDate() - (days - 1));
  const recent = s.daily.filter((d) => d.date >= cutoff.toISOString().slice(0, 10)).reverse();
  const periods = [[`Today (${longDate(s.today)})`, "today"], ["Last 7 days", "week"], ["Last 30 days", "month"], ["All time", "alltime"]] as const;
  const avg = comp.daily_avg_30;
  return (
    <main>
      <h1>Statistics</h1>
      <label>Metric{" "}
        <select value={metric} onChange={(e) => saveMetric.mutate(e.target.value as Metric)}>
          {METRICS.map((m) => <option key={m} value={m}>{LABELS[m]}</option>)}
        </select>
      </label>
      <Heatmap today={s.today} daily={s.daily} metric={metric} onPick={setPicked} />
      <p className="muted">Less {COLORS.map((c) => <span key={c} style={{ display: "inline-block", width: 13, height: 13, background: c }} />)} More</p>
      <table>
        <thead><tr><th>Period</th><th>Paragraphs</th><th>Source Chars</th><th>EN Words</th><th>vs prev</th></tr></thead>
        <tbody>
          {periods.map(([label, key]) => (
            <tr key={key}>
              <td>{label}</td><td>{n(s.summary[key].paragraphs)}</td><td>{n(s.summary[key].chars)}</td>
              <td>{n(s.summary[key].en_words)}</td><td>{key === "alltime" ? "—" : pct(comp.periods[key]?.pct_change)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p>Current streak: {s.streaks.current_streak} days · Longest streak: {s.streaks.longest_streak} days
        {best && best[metric] > 0 && <> · Best day: {longDate(best.date)} ({n(best[metric])} {UNITS[metric]})</>}</p>
      <p>Daily avg (30d): {avg < 10 ? avg.toFixed(1) : n(Math.round(avg))} {UNITS[metric]}</p>
      <button onClick={() => setDays(days === 30 ? 7 : 30)}>{days === 30 ? "Show Last 7 Days" : "Show Last 30 Days"}</button>
      <table>
        <thead><tr><th>Date</th><th>Paragraphs</th><th>Source Chars</th><th>EN Words</th></tr></thead>
        <tbody>
          {recent.map((d) => (
            <tr key={d.date} aria-current={d.date === picked ? "date" : undefined} className={d.date === picked ? "selected" : ""}>
              <td>{longDate(d.date)}</td><td>{n(d.paragraphs)}</td><td>{n(d.chars)}</td><td>{n(d.en_words)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <h2>By series</h2>
      {s.series.length ? (
        <table>
          <thead><tr><th>Series</th><th>Paragraphs</th><th>Source Chars</th><th>EN Words</th><th>Chapters</th></tr></thead>
          <tbody>
            {s.series.map((r) => (
              <tr key={r.series_id}><td>{r.series}</td><td>{n(r.paragraphs)}</td><td>{n(r.chars)}</td><td>{n(r.en_words)}</td><td>{r.chapters}</td></tr>
            ))}
          </tbody>
        </table>
      ) : <p className="muted">No series data yet.</p>}
      {saveMetric.error && <p className="error" role="alert">{saveMetric.error.message}</p>}
    </main>
  );
}
