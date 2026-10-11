import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { api, call } from "../api/client";
import Chapters from "./Chapters";
import FindReplace from "./FindReplace";
import { invalidateLibrary, useDocuments, useSeriesList } from "./queries";
import PhraseSuggestions from "./PhraseSuggestions";
import Volumes from "./Volumes";

export default function SeriesPage() {
  const seriesId = Number(useParams().id);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const all = useSeriesList();
  const docs = useDocuments();
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
  if (all.isPending || docs.isPending || profiles.isPending) return <main><p className="muted">Loading…</p></main>;
  const loadError = all.error ?? docs.error;
  if (loadError) return <main><p className="error" role="alert">{loadError.message}</p></main>;
  const series = all.data?.find((s) => s.id === seriesId);
  if (!series) return <main><p>No such series. <Link to="/">Back to the library</Link></p></main>;
  const chapters = (docs.data ?? [])
    .filter((d) => d.series_id === seriesId)
    .sort((a, b) => a.series_order - b.series_order || a.id - b.id);
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
    <main>
      <p><Link to="/">← Library</Link></p>
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
          <button type="button" disabled={remove.isPending} onClick={() => {
            if (window.confirm(`Delete series "${series.title}"? Its chapters are kept, unsorted.`)) remove.mutate();
          }}>Delete series</button>
        </div>
        {(save.error ?? remove.error) && <p className="error" role="alert">{(save.error ?? remove.error)!.message}</p>}
      </form>
      <Chapters seriesId={seriesId} docs={chapters} />
      <Volumes seriesId={seriesId} docs={chapters} />
      <FindReplace seriesId={seriesId} />
      <PhraseSuggestions seriesId={seriesId}
        defaultProfileId={series.profile_id ?? profiles.data?.find((p) => p.is_default)?.id ?? null} />
    </main>
  );
}
