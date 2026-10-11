import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, call } from "../api/client";
import type { Doc, SeriesRow } from "./group";
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
  const update = useMutation({
    mutationFn: (body: { title?: string; series_id?: number | null }) =>
      call(api.PATCH("/documents/{document_id}", { params: { path: { document_id: doc.id } }, body })),
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
      <td onDoubleClick={() => setEditing(true)}>
        {editing ? (
          <input autoFocus defaultValue={doc.title} aria-label="Title"
            onBlur={(e) => rename(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") rename(e.currentTarget.value);
              if (e.key === "Escape") setEditing(false);
            }} />
        ) : (
          doc.title
        )}
        {update.isError && <span className="error"> {update.error.message}</span>}
      </td>
      <td>{doc.progress}%</td>
      <td className="muted">{new Date(doc.updated_at).toLocaleString()}</td>
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
      </td>
    </tr>
  );
}
