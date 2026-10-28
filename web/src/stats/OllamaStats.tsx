import { useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { Link } from "react-router";
import { api, call } from "../api/client";
import { browserZone } from "../time";
import PageHeader from "../ui/PageHeader";
import { BAR_METRICS, barHeights, outcomePcts, type BarMetric } from "./ollamaBars";

const LABELS: Record<BarMetric, string> = { tokens_per_s: "Tokens/s", lines_per_hour: "Lines per hour", s_per_chunk: "s per chunk" };
const num = (v: number | null | undefined, digits = 1) =>
  v == null ? "—" : v.toLocaleString(undefined, { maximumFractionDigits: digits });
const pct = (v: number | null | undefined) => (v == null ? "—" : `${Math.round(v * 100)}%`);
const duration = (seconds: number) => {
  const m = Math.round(seconds / 60);
  return m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${m % 60} min`;
};
const shortDate = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { dateStyle: "medium" });

/** The Ollama tab: 30-day KPIs, a bar per finished run, a table per model and preset, and the recent runs. */
export default function OllamaStats({ tabs }: { tabs: ReactNode }) {
  const stats = useQuery({
    queryKey: ["stats", "ollama"],
    queryFn: () => call(api.GET("/stats/ollama", { params: { query: { tz: browserZone() } } })),
  });
  const [metric, setMetric] = useState<BarMetric>("tokens_per_s");
  const header = <PageHeader title="Statistics" />;
  if (stats.isPending) return <main className="stats">{header}{tabs}<p className="muted">Loading…</p></main>;
  if (stats.isError) return <main className="stats">{header}{tabs}<p className="error" role="alert">{stats.error.message}</p></main>;
  const s = stats.data;
  if (s.runs.length === 0 && s.by_model.length === 0) {
    return <main className="stats">{header}{tabs}<p className="muted panel-msg">No Ollama runs yet</p></main>;
  }
  const chronological = [...s.runs].reverse();
  const heights = barHeights(chronological.map((r) => r[metric]));
  const outcomes = outcomePcts(s.outcomes);
  return (
    <main className="stats">
      {header}
      {tabs}
      <div className="kpis">
        <section className="panel kpi" aria-label={`Tokens per second, 30 days: ${num(s.tokens_per_s_30d)}`}>
          <span className="label">Tokens/s, 30 days</span><b>{num(s.tokens_per_s_30d)}</b><span className="muted">average</span>
        </section>
        <section className="panel kpi" aria-label={`Lines translated, 30 days: ${num(s.lines_30d, 0)}`}>
          <span className="label">Lines, 30 days</span><b>{num(s.lines_30d, 0)}</b>
          <span className="muted">{num(s.chapters_30d, 0)} {s.chapters_30d === 1 ? "chapter" : "chapters"}</span>
        </section>
        <section className="panel kpi" aria-label={outcomes
          ? `Outcomes: ${outcomes.used}% used, ${outcomes.edited}% edited, ${outcomes.ignored}% ignored` : "Outcomes: none yet"}>
          <span className="label">Used or edited</span>
          <b>{outcomes ? `${outcomes.used + outcomes.edited}%` : "—"}</b>
          {outcomes ? (
            <>
              <span className="ostack" aria-hidden="true">
                <i className="used" style={{ width: `${outcomes.used}%` }} />
                <i className="edited" style={{ width: `${outcomes.edited}%` }} />
                <i className="ignored" style={{ width: `${outcomes.ignored}%` }} />
              </span>
              <span className="muted">{outcomes.used}% used · {outcomes.edited}% edited · {outcomes.ignored}% ignored</span>
            </>
          ) : <span className="muted">no outcomes yet</span>}
        </section>
        <section className="panel kpi" aria-label={`Retry rate, 30 days: ${pct(s.retry_rate_30d)}`}>
          <span className="label">Retry rate, 30 days</span><b>{pct(s.retry_rate_30d)}</b><span className="muted">chunks retried</span>
        </section>
      </div>

      <section className="panel" aria-labelledby="tokens-h">
        <div className="panel-head"><h2 id="tokens-h" className="label">Tokens</h2></div>
        <div className="table-scroll">
          <table className="token-totals">
            <thead><tr><th /><th className="num">Last 30 days</th><th className="num">All time</th></tr></thead>
            <tbody>
              <tr><th scope="row">Input (prompt)</th><td className="num">{num(s.tokens.d30.prompt_tokens, 0)}</td><td className="num">{num(s.tokens.all.prompt_tokens, 0)}</td></tr>
              <tr><th scope="row">Output</th><td className="num">{num(s.tokens.d30.output_tokens, 0)}</td><td className="num">{num(s.tokens.all.output_tokens, 0)}</td></tr>
              <tr className="total"><th scope="row">Total</th><td className="num">{num(s.tokens.d30.total_tokens, 0)}</td><td className="num">{num(s.tokens.all.total_tokens, 0)}</td></tr>
              <tr><th scope="row">Requests</th><td className="num">{num(s.tokens.d30.requests, 0)}</td><td className="num">{num(s.tokens.all.requests, 0)}</td></tr>
              <tr><th scope="row">Time answering</th><td className="num">{duration(s.tokens.d30.seconds)}</td><td className="num">{duration(s.tokens.all.seconds)}</td></tr>
              <tr><th scope="row">Prompt processing, tokens/s</th><td className="num">{num(s.tokens.d30.prompt_tokens_per_s)}</td><td className="num">{num(s.tokens.all.prompt_tokens_per_s)}</td></tr>
            </tbody>
          </table>
        </div>
        <p className="muted panel-msg">Every request counts, runs and the editor alike, including requests whose answer failed.</p>
      </section>

      <section className="panel" aria-labelledby="obars-h">
        <div className="panel-head">
          <h2 id="obars-h" className="label">Per run</h2>
          <div className="seg" role="group" aria-label="Run metric">
            {BAR_METRICS.map((m) => (
              <button key={m} type="button" aria-pressed={m === metric} onClick={() => setMetric(m)}>{LABELS[m]}</button>
            ))}
          </div>
        </div>
        {chronological.length ? (
          <div className="obars">
            {chronological.map((r, i) => (
              <div key={r.job_id} className={heights[i] > 0 ? "obar" : "obar none"}
                title={`${shortDate(r.date)}: ${num(r[metric])} ${LABELS[metric].toLowerCase()}`}>
                <i style={{ height: `${heights[i]}%` }} />
              </div>
            ))}
          </div>
        ) : <p className="muted panel-msg">No finished runs yet.</p>}
      </section>

      <section className="panel" aria-labelledby="models-h">
        <div className="panel-head"><h2 id="models-h" className="label">By model</h2></div>
        <div className="table-scroll">
          <table>
            <thead><tr><th>Model</th><th>Preset</th><th className="num">Runs</th><th className="num">Tokens/s</th><th className="num">s per chunk</th>
              <th className="num">Chunk lines</th><th className="num">Context lines</th><th className="num">Input tokens</th>
              <th className="num">Output tokens</th><th className="num">Used or edited</th></tr></thead>
            <tbody>
              {s.by_model.map((m) => (
                <tr key={`${m.model}|${m.preset}`}>
                  <td>{m.model}</td><td>{m.preset}</td><td className="num">{m.runs}</td><td className="num">{num(m.tokens_per_s)}</td>
                  <td className="num">{num(m.s_per_chunk)}</td><td className="num">{m.chunk_lines}</td><td className="num">{m.context_lines}</td>
                  <td className="num">{num(m.prompt_tokens, 0)}</td><td className="num">{num(m.output_tokens, 0)}</td>
                  <td className="num">{m.used_or_edited_pct == null ? "—" : `${Math.round(m.used_or_edited_pct)}%`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel" aria-labelledby="runs-h">
        <div className="panel-head">
          <h2 id="runs-h" className="label">Recent runs</h2>
          <Link to="/jobs?tab=history">Job history</Link>
        </div>
        <div className="table-scroll">
          <table>
            <thead><tr><th>Date</th><th className="num">Chapters</th><th className="num">Lines</th><th className="num">Duration</th>
              <th className="num">Tokens/s</th><th className="num">Lines per hour</th><th className="num">s per chunk</th>
              <th className="num">Input tokens</th><th className="num">Output tokens</th></tr></thead>
            <tbody>
              {s.runs.slice(0, 10).map((r) => (
                <tr key={r.job_id}>
                  <td><Link to="/jobs?tab=history">{shortDate(r.date)}</Link></td><td className="num">{r.chapters}</td>
                  <td className="num">{r.lines}</td><td className="num">{r.duration_s == null ? "—" : `${Math.round(r.duration_s / 60)} min`}</td>
                  <td className="num">{num(r.tokens_per_s)}</td><td className="num">{num(r.lines_per_hour, 0)}</td><td className="num">{num(r.s_per_chunk)}</td>
                  <td className="num">{num(r.prompt_tokens, 0)}</td><td className="num">{num(r.output_tokens, 0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}
