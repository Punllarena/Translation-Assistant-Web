import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { api, call } from "../api/client";
import BatchPublish from "../publish/BatchPublish";
import DocumentRow from "./DocumentRow";
import { groupDocuments, visibleSelection } from "./group";
import NewDocument from "./NewDocument";
import { invalidateLibrary, useDocuments, useSeriesList } from "./queries";

export default function Picker() {
  const queryClient = useQueryClient();
  const docs = useDocuments();
  const series = useSeriesList();
  const [filter, setFilter] = useState("");
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [creating, setCreating] = useState(false);
  const [batch, setBatch] = useState<number[] | null>(null);
  const done = () => {
    setSelected(new Set());
    return invalidateLibrary(queryClient);
  };
  const remove = useMutation({
    mutationFn: (ids: number[]) =>
      Promise.all(ids.map((id) =>
        call(api.DELETE("/documents/{document_id}", { params: { path: { document_id: id } } })))),
    onSettled: done,
  });
  const merge = useMutation({
    mutationFn: ({ ids, title }: { ids: number[]; title: string }) =>
      call(api.POST("/documents/merge", { body: { document_ids: ids, title } })),
    onSuccess: done,
  });
  const newSeries = useMutation({
    mutationFn: (title: string) => call(api.POST("/series", { body: { title, syosetu_url: "" } })),
    onSuccess: done,
  });
  if (docs.isPending || series.isPending) return <main><p className="muted">Loading…</p></main>;
  if (docs.isError || series.isError) {
    return <main><p className="error">{(docs.error ?? series.error)?.message}</p></main>;
  }
  const groups = groupDocuments(docs.data, series.data, filter);
  const visible = visibleSelection(selected, groups);
  const busy = merge.isPending || remove.isPending;
  const toggle = (id: number, on: boolean) => {
    const next = new Set(selected);
    if (on) next.add(id);
    else next.delete(id);
    setSelected(next);
  };
  const error = remove.error ?? merge.error ?? newSeries.error;
  return (
    <main>
      <div className="toolbar">
        <input type="search" placeholder="Filter" aria-label="Filter" value={filter}
          onChange={(e) => setFilter(e.target.value)} />
        <button onClick={() => setCreating(true)}>New document</button>
        <button onClick={() => {
          const title = window.prompt("Series title");
          if (title?.trim()) newSeries.mutate(title);
        }}>New series</button>
        <Link to="/import">Import…</Link>
        <button disabled={visible.length < 2 || busy} onClick={() => {
          const title = window.prompt("Chapter heading for the merged chapter (it keeps the first chapter's name)");
          if (title?.trim()) merge.mutate({ ids: visible, title });
        }}>Merge {visible.length || ""}</button>
        <button disabled={!visible.length || busy} onClick={() => {
          if (window.confirm(`Delete ${visible.length} document(s)? This cannot be undone.`)) {
            remove.mutate(visible);
          }
        }}>Delete {visible.length || ""}</button>
        <button disabled={!visible.length || busy} onClick={() => setBatch(visible)}>Publish {visible.length || ""}</button>
      </div>
      {error && <p className="error" role="alert">{error.message}</p>}
      {creating && <NewDocument series={series.data} onDone={() => setCreating(false)} />}
      {batch && <BatchPublish ids={batch} onClose={() => setBatch(null)} />}
      {groups.map((g) => (
        <section key={g.series?.id ?? "unsorted"}>
          <h2>
            {g.series ? <Link to={`/series/${g.series.id}`}>{g.series.title}</Link> : "Unsorted"}
          </h2>
          {g.docs.length ? (
            <table>
              <thead>
                <tr>
                  <th><span className="visually-hidden">Select</span></th>
                  <th>Title</th>
                  <th>Progress</th>
                  <th>Edited</th>
                  <th>WordPress</th>
                  <th>Series</th>
                  <th>Export</th>
                </tr>
              </thead>
              <tbody>
                {g.docs.map((d) => (
                  <DocumentRow key={d.id} doc={d} series={series.data}
                    selected={visible.includes(d.id)} onSelect={(on) => toggle(d.id, on)} />
                ))}
              </tbody>
            </table>
          ) : (
            <p className="muted">No chapters yet.</p>
          )}
        </section>
      ))}
    </main>
  );
}
