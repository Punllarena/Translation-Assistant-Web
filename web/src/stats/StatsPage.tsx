import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, call } from "../api/client";
import { browserZone } from "../time";
import PageHeader from "../ui/PageHeader";
import Heatmap from "./Heatmap";
import { LEVELS, METRICS, type Metric } from "./heatmapGrid";

const LABELS: Record<Metric, string> = { paragraphs: "Paragraphs", chars: "Source chars", en_words: "EN words" };
const UNITS: Record<Metric, string> = { paragraphs: "paragraphs", chars: "source chars", en_words: "EN words" };
const n = (v: number) => v.toLocaleString();
const pct = (v: number | null | undefined) => (v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(0)}%`);
const trend = (v: number | null | undefined) => (v == null || v === 0 ? "" : v > 0 ? "up" : "down");
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
  const avgText = avg < 10 ? avg.toFixed(1) : n(Math.round(avg));
  const { current_streak: streak, longest_streak: longest } = s.streaks;
  return (
    <main className="stats">
      <PageHeader title="Statistics" actions={
        <div className="seg" role="group" aria-label="Metric">
          {METRICS.map((m) => (
            <button key={m} type="button" aria-pressed={m === metric} onClick={() => saveMetric.mutate(m)}>{LABELS[m]}</button>
          ))}
        </div>
      } />
      {saveMetric.error && <p className="error" role="alert">{saveMetric.error.message}</p>}

      <div className="kpis">
        <section className="panel kpi" aria-label={`Current streak: ${streak} days`}>
          <span className="label">Current streak</span><b>{streak} days</b><span className="muted">Longest: {longest} days</span>
        </section>
        <section className="panel kpi" aria-label={`Daily average over 30 days: ${avgText} ${UNITS[metric]}`}>
          <span className="label">Daily average, 30 days</span><b>{avgText}</b><span className="muted">{UNITS[metric]} per day</span>
        </section>
        {best && best[metric] > 0 && (
          <section className="panel kpi" aria-label={`Best day: ${n(best[metric])} ${UNITS[metric]} on ${longDate(best.date)}`}>
            <span className="label">Best day</span><b>{n(best[metric])}</b>
            <span className="muted">{UNITS[metric]} · {longDate(best.date)}</span>
          </section>
        )}
      </div>

      <section className="panel pad" aria-labelledby="heat-h">
        <div className="heat-head">
          <h2 id="heat-h" className="label">Translated per day, last 52 weeks</h2>
          <span className="legend" aria-hidden="true">Less {LEVELS.map((l) => <i key={l} className={`swatch heat-${l}`} />)} More</span>
        </div>
        <Heatmap today={s.today} daily={s.daily} metric={metric} onPick={setPicked} />
      </section>

      <section className="panel" aria-labelledby="period-h">
        <div className="panel-head"><h2 id="period-h" className="label">By period</h2></div>
        <div className="table-scroll">
          <table>
            <thead><tr><th>Period</th><th className="num">Paragraphs</th><th className="num">Source chars</th><th className="num">EN words</th><th className="num">vs previous</th></tr></thead>
            <tbody>
              {periods.map(([label, key]) => {
                const change = key === "alltime" ? null : comp.periods[key]?.pct_change;
                return (
                  <tr key={key}>
                    <td>{label}</td><td className="num">{n(s.summary[key].paragraphs)}</td><td className="num">{n(s.summary[key].chars)}</td>
                    <td className="num">{n(s.summary[key].en_words)}</td><td className={`num ${trend(change)}`}>{pct(change)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel" aria-labelledby="days-h">
        <div className="panel-head">
          <h2 id="days-h" className="label">Last {days} days</h2>
          <button type="button" className="small" onClick={() => setDays(days === 30 ? 7 : 30)}>{days === 30 ? "Show last 7 days" : "Show last 30 days"}</button>
        </div>
        <div className="table-scroll">
          <table>
            <thead><tr><th>Date</th><th className="num">Paragraphs</th><th className="num">Source chars</th><th className="num">EN words</th></tr></thead>
            <tbody>
              {recent.map((d) => (
                <tr key={d.date} aria-current={d.date === picked ? "date" : undefined} className={d.date === picked ? "selected" : ""}>
                  <td>{longDate(d.date)}</td><td className="num">{n(d.paragraphs)}</td><td className="num">{n(d.chars)}</td><td className="num">{n(d.en_words)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel" aria-labelledby="series-h">
        <div className="panel-head"><h2 id="series-h" className="label">By series</h2></div>
        {s.series.length ? (
          <div className="table-scroll">
            <table>
              <thead><tr><th>Series</th><th className="num">Paragraphs</th><th className="num">Source chars</th><th className="num">EN words</th><th className="num">Chapters</th></tr></thead>
              <tbody>
                {s.series.map((r) => (
                  <tr key={r.series_id}><td>{r.series}</td><td className="num">{n(r.paragraphs)}</td><td className="num">{n(r.chars)}</td><td className="num">{n(r.en_words)}</td><td className="num">{r.chapters}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <p className="muted panel-msg">No series data yet.</p>}
      </section>
    </main>
  );
}
