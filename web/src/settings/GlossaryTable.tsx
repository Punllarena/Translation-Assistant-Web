import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, ApiError, call, errorMessage } from "../api/client";
import { moveRow, toEntries, type Row } from "./glossary";

/** Editable glossary for one profile (desktop dlg_glossary). Keyed by the parent on profile + data version. */
type Props = { pid: number; loaded: Row[]; onLoaded: (rows: Row[]) => void; note: string | null; setNote: (n: string | null) => void };

function Editor({ pid, loaded, onLoaded, note, setNote }: Props) {
  const queryClient = useQueryClient();
  const [rows, setRows] = useState<Row[]>(loaded);
  const dirty = JSON.stringify(rows) !== JSON.stringify(loaded);
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
  const error = save.error?.message ?? upload.error?.message;
  return (
    <>
      {error && <p className="error" role="alert">{error}</p>}
      {note && <p role="status">{note}</p>}
      <table>
        <thead><tr><th>Phrase</th><th>Translation</th><th /></tr></thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              <td><input aria-label={`Phrase ${i + 1}`} value={r.phrase} onChange={(e) => edit(i, { phrase: e.target.value })} /></td>
              <td><input aria-label={`Translation ${i + 1}`} value={r.translation} onChange={(e) => edit(i, { translation: e.target.value })} /></td>
              <td className="toolbar">
                <button aria-label={`Move ${i + 1} up`} onClick={() => setRows(moveRow(rows, i, -1))}>↑</button>
                <button aria-label={`Move ${i + 1} down`} onClick={() => setRows(moveRow(rows, i, 1))}>↓</button>
                <button aria-label={`Remove ${i + 1}`} onClick={() => setRows(rows.filter((_, k) => k !== i))}>✕</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="toolbar">
        <button onClick={() => setRows([...rows, { phrase: "", translation: "" }])}>Add row</button>
        <button onClick={() => save.mutate()} disabled={save.isPending || !dirty}>Save glossary</button>
        <label>
          Import CSV{" "}
          <input
            type="file"
            accept=".csv,text/csv"
            aria-label="Import CSV"
            onChange={(e) => {
              const file = e.target.files?.[0];
              e.target.value = "";
              if (file && (!dirty || window.confirm("Discard unsaved glossary edits?"))) upload.mutate(file);
            }}
          />
        </label>
      </div>
    </>
  );
}

export default function GlossaryTable({ pid }: { pid: number }) {
  const queryClient = useQueryClient();
  const [note, setNote] = useState<string | null>(null); // outlives Editor remounts on data change
  const glossary = useQuery({
    queryKey: ["glossary", pid],
    queryFn: () => call(api.GET("/profiles/{profile_id}/glossary", { params: { path: { profile_id: pid } } })),
  });
  if (glossary.error) return <p className="error" role="alert">{glossary.error.message}</p>;
  if (!glossary.data) return <p className="muted">Loading…</p>;
  const loaded = glossary.data.map(({ phrase, translation }) => ({ phrase, translation }));
  return (
    <Editor
      key={`${pid}:${glossary.dataUpdatedAt}`}
      pid={pid}
      loaded={loaded}
      note={note}
      setNote={setNote}
      onLoaded={(rows) => queryClient.setQueryData(["glossary", pid], rows.map((r, i) => ({ ...r, id: i, sort_order: i })))}
    />
  );
}
