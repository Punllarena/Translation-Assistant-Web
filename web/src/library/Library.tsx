import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router";
import { api, call } from "../api/client";
import PageHeader from "../ui/PageHeader";
import { PromptDialog } from "../ui/Dialog";
import { invalidateLibrary, useAllVolumes, useDocuments, useSeriesList } from "./queries";
import { CompactList, Shelf } from "./SeriesCards";
import { seriesCards } from "./shelf";
import { readView, writeView, type LibraryView } from "./viewPref";

export default function Library() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const docs = useDocuments();
  const series = useSeriesList();
  const volumes = useAllVolumes();
  const [filter, setFilter] = useState("");
  const [view, setView] = useState<LibraryView>(() => readView());
  const [creating, setCreating] = useState(false);
  const create = useMutation({
    mutationFn: (title: string) => call(api.POST("/series", { body: { title, syosetu_url: "" } })),
    onSuccess: async (s) => {
      await invalidateLibrary(queryClient);
      setCreating(false);
      navigate(`/series/${s.id}`);
    },
  });
  const cards = useMemo(
    () => (docs.data && series.data && volumes.data ? seriesCards(series.data, docs.data, volumes.data, filter) : []),
    [docs.data, series.data, volumes.data, filter],
  );
  const pick = (v: LibraryView) => { setView(v); writeView(v); };

  const newSeries = (
    <button className="primary" onClick={() => { create.reset(); setCreating(true); }}>New series</button>
  );
  const importLink = <Link className="btn" to="/import">Import…</Link>;
  const failed = docs.error ?? series.error ?? volumes.error;
  const pending = docs.isPending || series.isPending || volumes.isPending;
  const empty = !pending && !failed && (series.data?.length ?? 0) === 0;

  return (
    <main className="library">
      <PageHeader title="Library" actions={
        <>
          <input type="search" aria-label="Search series" placeholder="Search series" value={filter}
            onChange={(e) => setFilter(e.target.value)} />
          <div className="seg" role="group" aria-label="View">
            <button type="button" aria-pressed={view === "shelf"} onClick={() => pick("shelf")}>Bookshelf</button>
            <button type="button" aria-pressed={view === "list"} onClick={() => pick("list")}>List</button>
          </div>
          {importLink}
          {newSeries}
        </>
      } />
      {pending && <p className="muted">Loading…</p>}
      {failed && <p className="error" role="alert">{failed.message}</p>}
      {empty && (
        <div className="library-empty">
          <p className="muted">No series yet.</p>
          <div className="library-empty-actions">{newSeries}{importLink}</div>
        </div>
      )}
      {!pending && !failed && !empty && cards.length === 0 && <p className="muted">No series match "{filter}".</p>}
      {cards.length > 0 && (view === "shelf" ? <Shelf cards={cards} /> : <CompactList cards={cards} />)}
      {creating && (
        <PromptDialog title="New series" label="Series title" confirmLabel="Create" busy={create.isPending}
          error={create.error?.message} onSubmit={(t) => create.mutate(t.trim())} onClose={() => setCreating(false)} />
      )}
    </main>
  );
}
