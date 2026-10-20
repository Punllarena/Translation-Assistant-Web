import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router";
import { api, call } from "../api/client";
import { ConfirmDialog } from "../ui/Dialog";
import { invalidateLibrary } from "./queries";
import SeriesWp from "./SeriesWp";
import type { SeriesRow } from "./shelf";

export default function SeriesSettings({ series, chapterCount }: { series: SeriesRow; chapterCount: number }) {
  const seriesId = series.id;
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [confirming, setConfirming] = useState(false);
  const profiles = useQuery({ queryKey: ["profiles"], queryFn: () => call(api.GET("/profiles")) });
  const save = useMutation({
    mutationFn: (body: { title: string; syosetu_url: string; profile_id: number | null }) =>
      call(api.PATCH("/series/{series_id}", { params: { path: { series_id: seriesId } }, body })),
    onSuccess: () => invalidateLibrary(queryClient),
  });
  const remove = useMutation({
    mutationFn: () => call(api.DELETE("/series/{series_id}", { params: { path: { series_id: seriesId } } })),
    onSuccess: async () => {
      await invalidateLibrary(queryClient);
      navigate("/");
    },
  });
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const profile = String(form.get("profile_id") ?? "");
    save.mutate({
      title: String(form.get("title")),
      syosetu_url: String(form.get("syosetu_url")),
      profile_id: profile ? Number(profile) : null,
    });
  };
  return (
    <>
      <form className="stack" onSubmit={submit} key={series.id}>
        <label>Title <input name="title" defaultValue={series.title} required /></label>
        <label>Series URL <input name="syosetu_url" type="url" defaultValue={series.syosetu_url} /></label>
        <label>
          Profile{" "}
          <select name="profile_id" defaultValue={series.profile_id ?? ""}>
            <option value="">Default profile</option>
            {(profiles.data ?? []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </label>
        {profiles.isError && <p className="error" role="alert">{profiles.error.message}</p>}
        <div className="toolbar">
          <button disabled={save.isPending || !profiles.isSuccess}>Save</button>
          <a href={`/api/series/${seriesId}/export/markdown?variant=plain`} download>Markdown ZIP (complete chapters only)</a>
          <a href={`/api/series/${seriesId}/export/markdown?variant=ruby`} download>Ruby Markdown ZIP (complete chapters only)</a>
        </div>
        {save.error && <p className="error" role="alert">{save.error.message}</p>}
      </form>
      <SeriesWp series={series} />
      <section className="danger-zone">
        <h2>Danger zone</h2>
        <button type="button" className="danger" onClick={() => { remove.reset(); setConfirming(true); }}>Delete series</button>
      </section>
      {confirming && (
        <ConfirmDialog
          title="Delete series"
          message={`Delete "${series.title}" and its ${chapterCount} chapters? This can't be undone.`}
          confirmLabel={`Delete series and ${chapterCount} chapters`}
          danger
          busy={remove.isPending}
          error={remove.error?.message}
          onConfirm={() => remove.mutate()}
          onClose={() => setConfirming(false)}
        />
      )}
    </>
  );
}
