import { useMemo, useState } from "react";
import { Link } from "react-router";
import PageHeader from "../ui/PageHeader";
import { useAccountPref } from "../settings/useAccountPref";
import { useAllVolumes, useDocuments, useSeriesList } from "./queries";
import { CompactList, Shelf } from "./SeriesCards";
import { FilterChips, FiltersButton, SortControl } from "./LibraryFilters";
import { DEFAULT_FILTERS, DEFAULT_SORT, emptyReason, filterCards, sortCards } from "./libraryQuery";
import { parseFilters, parseSort } from "./libraryPrefs";
import { seriesCards } from "./shelf";
import { parseView } from "./viewPref";

export default function Library() {
  const docs = useDocuments();
  const series = useSeriesList();
  const volumes = useAllVolumes();
  const [filter, setFilter] = useState("");
  const [view, setView] = useAccountPref({
    key: "library_view", local: "ta.libraryView", localFormat: "text",
    parse: parseView, fallback: "shelf",
  });
  const [sort, setSort] = useAccountPref({
    key: "library_sort", local: "ta.librarySort", parse: parseSort, fallback: DEFAULT_SORT,
  });
  const [filters, setFilters] = useAccountPref({
    key: "library_filters", local: "ta.libraryFilters", parse: parseFilters, fallback: DEFAULT_FILTERS,
  });
  const all = useMemo(
    () => (docs.data && series.data && volumes.data ? seriesCards(series.data, docs.data, volumes.data) : []),
    [docs.data, series.data, volumes.data],
  );
  const cards = useMemo(() => sortCards(filterCards(all, filters, filter), sort), [all, filters, filter, sort]);

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
          <SortControl sort={sort} onChange={setSort} />
          <FiltersButton filters={filters} onChange={setFilters} />
          <div className="seg" role="group" aria-label="View">
            <button type="button" aria-pressed={view === "shelf"} onClick={() => setView("shelf")}>Bookshelf</button>
            <button type="button" aria-pressed={view === "list"} onClick={() => setView("list")}>List</button>
          </div>
          {importLink}
          {newSeries}
        </>
      } />
      {!pending && !failed && all.length > 0 && (
        <FilterChips filters={filters} onChange={setFilters} shown={cards.length} total={all.length} />
      )}
      {pending && <p className="muted">Loading…</p>}
      {failed && <p className="error" role="alert">{failed.message}</p>}
      {empty && (
        <div className="library-empty">
          <p className="muted">No series yet.</p>
          <div className="library-empty-actions">{newSeries}{importLink}</div>
        </div>
      )}
      {!pending && !failed && !empty && cards.length === 0 && (() => {
        const reason = emptyReason(all, filters, filter);
        return (
        reason === "all-archived" ? (
          <div className="library-empty">
            <p className="muted">All your series are archived.</p>
            <button type="button" onClick={() => setFilters({ ...filters, archived: "include" })}>Show archived</button>
          </div>
        ) : reason === "search" ? (
          <p className="muted">No series match "{filter}".</p>
        ) : (
          <div className="library-empty">
            <p className="muted">No series match these filters.</p>
            <button type="button" onClick={() => setFilters(DEFAULT_FILTERS)}>Clear all</button>
          </div>
        )
        );
      })()}
      {cards.length > 0 && (view === "shelf" ? <Shelf cards={cards} /> : <CompactList cards={cards} />)}
    </main>
  );
}
