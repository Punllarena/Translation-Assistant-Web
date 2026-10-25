import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link } from "react-router";
import { api, call, type Schemas } from "../api/client";
import { slugify, tocUrl } from "../publish/wp";
import { invalidateLibrary } from "./queries";
import { summaryStatus } from "./summaryStatus";

/** The series' WordPress tab: publishing fields (slug, short title, password, unlock) and the ToC-page summary. */
export default function SeriesWp({ series }: { series: Schemas["SeriesOut"] }) {
  const queryClient = useQueryClient();
  const creds = useQuery({ queryKey: ["wp", "credentials"], queryFn: () => call(api.GET("/credentials")) });
  const endpoint = creds.data?.find((c) => c.kind === "wordpress" && c.name === "")?.endpoint_url ?? "";
  const [summary, setSummary] = useState(series.wp_summary);
  const patch = (body: Schemas["SeriesUpdate"]) =>
    call(api.PATCH("/series/{series_id}", { params: { path: { series_id: series.id } }, body }));
  const save = useMutation({ mutationFn: patch, onSuccess: () => invalidateLibrary(queryClient) });
  const saveSummary = useMutation({ mutationFn: patch, onSuccess: () => invalidateLibrary(queryClient) });
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const pw = String(f.get("pw"));
    const unlock = String(f.get("unlock") ?? "").trim();
    save.mutate({
      wp_series_slug: String(f.get("slug") ?? "").trim(),
      wp_series_title_short: String(f.get("short") ?? "").trim(),
      wp_password_enabled: pw === "" ? null : pw === "on",
      wp_unlock_after: unlock === "" ? null : Number(unlock),
    });
  };
  const pwValue = series.wp_password_enabled === null ? "" : series.wp_password_enabled ? "on" : "off";
  const status = summaryStatus({ text: series.wp_summary, pending: series.wp_summary_pending, error: series.wp_summary_error });
  const toneClass = status.tone === "ok" ? "saved-note" : status.tone;
  return (
    <div className="series-sections">
      <section className="panel pad">
        <h2>Publishing</h2>
        {creds.isSuccess && !endpoint && (
          <p className="hint">Set your WordPress endpoint and API key in <Link to="/settings/wp">Settings → WordPress</Link> to publish.</p>
        )}
        <form className="stack" key={`${series.id}-${series.wp_series_slug}-${series.wp_series_title_short}`} onSubmit={submit}>
          <div className="row-fields">
            <label className="field"><span>Series slug</span>
              <input name="slug" defaultValue={series.wp_series_slug || slugify(series.title)} /></label>
            <label className="field"><span>Short title</span>
              <input name="short" defaultValue={series.wp_series_title_short} /></label>
          </div>
          <div className="row-fields">
            <label className="field"><span>Password protection</span>
              <select name="pw" defaultValue={pwValue}>
                <option value="">Use my default</option>
                <option value="on">On</option>
                <option value="off">Off</option>
              </select>
            </label>
            <label className="field"><span>Keep N chapters locked</span>
              <input name="unlock" type="number" min={1} placeholder="my default" defaultValue={series.wp_unlock_after ?? ""} /></label>
          </div>
          <div className="toolbar">
            <button disabled={save.isPending}>Save WordPress fields</button>
            {endpoint && series.wp_series_slug && (
              <a href={tocUrl(endpoint, series.wp_series_slug)} target="_blank" rel="noreferrer">Open TOC page</a>
            )}
          </div>
          {save.error && <p className="error" role="alert">{save.error.message}</p>}
        </form>
      </section>
      <section className="panel pad">
        <h2>Series summary (ToC page)</h2>
        <p className="hint">Shown on the series' table-of-contents page. Paragraphs are separated by a blank line.</p>
        <textarea className="summary" rows={10} aria-label="Series summary" value={summary}
          onChange={(e) => setSummary(e.target.value)} />
        <div className="toolbar">
          <button type="button" disabled={saveSummary.isPending || summary === series.wp_summary}
            onClick={() => saveSummary.mutate({ wp_summary: summary })}>Save summary</button>
        </div>
        <p className={toneClass} role="status">{status.message}</p>
        {saveSummary.error && <p className="error" role="alert">{saveSummary.error.message}</p>}
      </section>
    </div>
  );
}
