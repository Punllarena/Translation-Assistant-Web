import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, ApiError, call, errorMessage } from "../api/client";
import { ArrowDown, ArrowUp, Cross } from "../ui/icons";
import { changedRows, countChanges, moveRow, toEntries, type Row } from "./glossary";

/** Editable glossary for one profile (desktop dlg_glossary). Keyed by the parent on profile + data version. */
type Props = { pid: number; loaded: Row[]; onLoaded: (rows: Row[]) => void; onDirty: (d: boolean) => void; note: string | null; setNote: (n: string | null) => void };

const Heading = () => <h2 id="glossary-h">Glossary</h2>;

function Editor({ pid, loaded, onLoaded, onDirty, note, setNote }: Props) {
  const queryClient = useQueryClient();
  const [rows, setRows] = useState<Row[]>(loaded);
  const dirty = JSON.stringify(rows) !== JSON.stringify(loaded);
  const changed = changedRows(rows, loaded);
  const changes = countChanges(rows, loaded);
  useEffect(() => {
    onDirty(dirty);
    return () => onDirty(false);
  }, [dirty, onDirty]);
  const written = () => queryClient.invalidateQueries({ queryKey: ["document"] });
  const save = useMutation({
    mutationFn: () =>
      call(api.PUT("/profiles/{profile_id}/glossary", { params: { path: { profile_id: pid } }, body: { entries: toEntries(rows) } })),
    onSuccess: (data) => {
      onLoaded(data.map(({ phrase, translation }) => ({ phrase, translation })));
      setNote("Saved");
      written();
    },
    onError: () => setNote(null),
  });
  const upload = useMutation({
    mutationFn: async (file: File) => {
      const body = new FormData();
      body.append("file", file);
      const res = await fetch(`/api/profiles/${pid}/glossary/import`, { method: "POST", body });
      if (!res.ok) throw new ApiError(res.status, errorMessage(await res.json().catch(() => null)));
      return (await res.json()) as { added: number; updated: number; skipped: number };
    },
    onSuccess: (r) => {
      setNote(`Imported: ${r.added} added, ${r.updated} updated, ${r.skipped} skipped`);
      queryClient.invalidateQueries({ queryKey: ["glossary", pid] });
      written();
    },
    onError: () => setNote(null),
  });
  const edit = (i: number, patch: Partial<Row>) => setRows(rows.map((r, k) => (k === i ? { ...r, ...patch } : r)));
  const discard = () => {
    if (!window.confirm("Discard unsaved glossary edits?")) return;
    setRows(loaded);
    setNote(null);
  };
  const error = save.error?.message ?? upload.error?.message;
  return (
    <section className="panel glossary" aria-labelledby="glossary-h">
      <div className="panel-head">
        <div className="title-row"><Heading /><span className="muted">{loaded.length} terms</span></div>
        {changes > 0 && (
          <span className="unsaved" aria-live="polite">
            <span className="dot seal" aria-hidden="true" />{changes} unsaved {changes === 1 ? "change" : "changes"}
          </span>
        )}
      </div>
      {error && <p className="error panel-msg" role="alert">{error}</p>}
      {note && <p className="panel-msg" role="status">{note}</p>}
      <div className="table-scroll">
        <table className="glossary-table">
          <thead><tr><th>Phrase</th><th>Translation</th><th><span className="visually-hidden">Row actions</span></th></tr></thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} className={changed.has(i) ? "changed" : undefined}>
                <td><input className="jp" lang="ja" aria-label={`Phrase ${i + 1}`} value={r.phrase} onChange={(e) => edit(i, { phrase: e.target.value })} /></td>
                <td><input className="en" aria-label={`Translation ${i + 1}`} value={r.translation} onChange={(e) => edit(i, { translation: e.target.value })} /></td>
                <td className="row-actions">
                  <button type="button" className="icon" aria-label={`Move ${i + 1} up`} disabled={i === 0} onClick={() => setRows(moveRow(rows, i, -1))}><ArrowUp /></button>
                  <button type="button" className="icon" aria-label={`Move ${i + 1} down`} disabled={i === rows.length - 1} onClick={() => setRows(moveRow(rows, i, 1))}><ArrowDown /></button>
                  <button type="button" className="icon" aria-label={`Remove ${i + 1}`} onClick={() => setRows(rows.filter((_, k) => k !== i))}><Cross /></button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="panel-foot">
        <button type="button" onClick={() => setRows([...rows, { phrase: "", translation: "" }])}>Add row</button>
        <label className="btn file-btn">
          Import CSV
          <input type="file" accept=".csv,text/csv" aria-label="Import CSV" className="visually-hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              e.target.value = "";
              if (file && (!dirty || window.confirm("Discard unsaved glossary edits?"))) upload.mutate(file);
            }} />
        </label>
        <span className="spacer" />
        <button type="button" className="quiet" disabled={!dirty} onClick={discard}>Discard</button>
        <button type="button" className="primary" onClick={() => save.mutate()} disabled={save.isPending || !dirty}>Save glossary</button>
      </div>
    </section>
  );
}

export default function GlossaryTable({ pid, onDirty }: { pid: number; onDirty: (d: boolean) => void }) {
  const queryClient = useQueryClient();
  const [note, setNote] = useState<string | null>(null); // outlives Editor remounts on data change
  const glossary = useQuery({
    queryKey: ["glossary", pid],
    queryFn: () => call(api.GET("/profiles/{profile_id}/glossary", { params: { path: { profile_id: pid } } })),
  });
  if (!glossary.data) {
    return (
      <section className="panel glossary" aria-labelledby="glossary-h">
        <div className="panel-head"><Heading /></div>
        {glossary.error
          ? <p className="error panel-msg" role="alert">{glossary.error.message}</p>
          : <p className="muted panel-msg">Loading…</p>}
      </section>
    );
  }
  const loaded = glossary.data.map(({ phrase, translation }) => ({ phrase, translation }));
  return (
    <Editor
      key={`${pid}:${glossary.dataUpdatedAt}`}
      pid={pid}
      loaded={loaded}
      onDirty={onDirty}
      note={note}
      setNote={setNote}
      onLoaded={(rows) => queryClient.setQueryData(["glossary", pid], rows.map((r, i) => ({ ...r, id: i, sort_order: i })))}
    />
  );
}
