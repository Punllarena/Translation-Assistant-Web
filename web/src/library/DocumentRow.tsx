import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { Link } from "react-router";
import { api, ApiError, call } from "../api/client";
import type { Doc, SeriesRow } from "./group";
import PublishDialog from "../publish/PublishDialog";
import { wpBadge } from "../publish/badge";
import { invalidateLibrary } from "./queries";

interface Props {
  doc: Doc;
  series: SeriesRow[];
  selected: boolean;
  onSelect: (checked: boolean) => void;
}

/** One picker row: select, rename in place (double-click), move to a series, export. */
export default function DocumentRow({ doc, series, selected, onSelect }: Props) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const settled = useRef(false);
  const update = useMutation({
    mutationFn: (body: { title?: string; series_id?: number | null }) =>
      call(api.PATCH("/documents/{document_id}", { params: { path: { document_id: doc.id } }, body })),
    onSuccess: () => invalidateLibrary(queryClient),
  });
  const refetch = useMutation({
    mutationFn: async () => {
      if (!window.confirm(`Re-fetch content from: ${doc.source_url}? Existing translations will be preserved by line position.`)) return;
      const send = (force: boolean) =>
        call(api.POST("/documents/{document_id}/refetch", { params: { path: { document_id: doc.id } }, body: { force } }));
      try {
        await send(false);
      } catch (e) {
        if (!(e instanceof ApiError) || e.status !== 409) throw e;
        if (!window.confirm(`${e.message}\n\nReplace anyway?`)) return;
        await send(true);
      }
    },
    onSuccess: () => invalidateLibrary(queryClient),
  });
  const rename = (title: string) => {
    setEditing(false);
    if (title.trim() && title !== doc.title) update.mutate({ title });
  };
  const exportUrl = (format: string) => `/api/documents/${doc.id}/export?format=${format}`;
  return (
    <tr>
      <td>
        <input type="checkbox" aria-label={`Select ${doc.title}`} checked={selected}
          onChange={(e) => onSelect(e.target.checked)} />
      </td>
      <td onDoubleClick={() => { settled.current = false; setEditing(true); }}>
        {editing ? (
          <input autoFocus defaultValue={doc.title} aria-label={`New title for ${doc.title}`}
            onBlur={(e) => { if (!settled.current) rename(e.target.value); }}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                settled.current = true;
                rename(e.currentTarget.value);
              }
              if (e.key === "Escape") {
                settled.current = true;
                setEditing(false);
              }
            }} />
        ) : (
          <>
            {doc.title}{" "}
            <Link to={`/documents/${doc.id}`} aria-label={`Open ${doc.title}`}>Open</Link>
          </>
        )}
        {doc.source_url && (
          <>{" "}<button type="button" disabled={refetch.isPending} onClick={() => refetch.mutate()}>Re-fetch</button></>
        )}
        {refetch.isError && <span className="error" role="alert"> {refetch.error.message}</span>}
        {update.isError && <span className="error"> {update.error.message}</span>}
      </td>
      <td>{doc.progress}%</td>
      <td className="muted">{new Date(doc.updated_at).toLocaleString()}</td>
      <td className="muted">{wpBadge(doc)}</td>
      <td>
        <select aria-label="Series" value={doc.series_id ?? ""}
          onChange={(e) => update.mutate({ series_id: e.target.value ? Number(e.target.value) : null })}>
          <option value="">Unsorted</option>
          {series.map((s) => <option key={s.id} value={s.id}>{s.title}</option>)}
        </select>
      </td>
      <td>
        <a href={exportUrl("txt")} download>TXT</a>{" "}
        <a href={exportUrl("md")} download>MD</a>{" "}
        <a href={exportUrl("md-ruby")} download>Ruby MD</a>
        {doc.series_id !== null && <>{" "}<button type="button" onClick={() => setPublishing(true)}>Publish…</button></>}
        {publishing && <PublishDialog doc={doc} onClose={() => setPublishing(false)} />}
      </td>
    </tr>
  );
}
