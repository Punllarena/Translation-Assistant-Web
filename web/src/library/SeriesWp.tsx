import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { FormEvent } from "react";
import { api, call, type Schemas } from "../api/client";
import { slugify, tocUrl } from "../publish/wp";
import { invalidateLibrary } from "./queries";

/** A series' WordPress fields: slug, short title, password override (inherit/on/off), unlock-after override. */
export default function SeriesWp({ series }: { series: Schemas["SeriesOut"] }) {
  const queryClient = useQueryClient();
  const creds = useQuery({ queryKey: ["wp", "credentials"], queryFn: () => call(api.GET("/credentials")) });
  const endpoint = creds.data?.find((c) => c.kind === "wordpress" && c.name === "")?.endpoint_url ?? "";
  const save = useMutation({
    mutationFn: (body: Schemas["SeriesUpdate"]) =>
      call(api.PATCH("/series/{series_id}", { params: { path: { series_id: series.id } }, body })),
    onSuccess: () => invalidateLibrary(queryClient),
  });
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
  return (
    <section>
      <h2>WordPress</h2>
      <form className="stack" key={`${series.id}-${series.wp_series_slug}-${series.wp_series_title_short}`} onSubmit={submit}>
        <label>Series slug <input name="slug" defaultValue={series.wp_series_slug || slugify(series.title)} /></label>
        <label>Short title <input name="short" defaultValue={series.wp_series_title_short} /></label>
        <label>Password protection{" "}
          <select name="pw" defaultValue={pwValue}>
            <option value="">Use my default</option>
            <option value="on">On</option>
            <option value="off">Off</option>
          </select>
        </label>
        <label>Keep N chapters locked <input name="unlock" type="number" min={0} placeholder="my default"
          defaultValue={series.wp_unlock_after ?? ""} /></label>
        <div className="toolbar">
          <button disabled={save.isPending}>Save WordPress fields</button>
          {endpoint && series.wp_series_slug && (
            <a href={tocUrl(endpoint, series.wp_series_slug)} target="_blank" rel="noreferrer">Open TOC page</a>
          )}
        </div>
        {save.error && <p className="error" role="alert">{save.error.message}</p>}
      </form>
    </section>
  );
}
