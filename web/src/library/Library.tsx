import { useMemo, useState } from "react";
import { Link } from "react-router";
import PageHeader from "../ui/PageHeader";
import { useAllVolumes, useDocuments, useSeriesList } from "./queries";
import { CompactList, Shelf } from "./SeriesCards";
import { seriesCards } from "./shelf";
import { readView, writeView, type LibraryView } from "./viewPref";

export default function Library() {
  const docs = useDocuments();
  const series = useSeriesList();
  const volumes = useAllVolumes();
  const [filter, setFilter] = useState("");
  const [view, setView] = useState<LibraryView>(() => readView());
  const cards = useMemo(
    () => (docs.data && series.data && volumes.data ? seriesCards(series.data, docs.data, volumes.data, filter) : []),
    [docs.data, series.data, volumes.data, filter],
  );
  const pick = (v: LibraryView) => { setView(v); writeView(v); };

  const newSeries = <Link className="btn primary" to="/new">New series</Link>;
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
    </main>
  );
}
