import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { api, call, type Schemas } from "../api/client";
import type { Doc } from "./group";
import { invalidateLibrary } from "./queries";

type Volume = Schemas["VolumeOut"];
const EPUB_FIELDS = [
  ["epub_title", "EPUB title"], ["epub_author", "Author"], ["epub_language", "Language"],
  ["epub_illustrator", "Illustrator"], ["epub_publisher", "Publisher"],
  ["epub_identifier", "Identifier"], ["epub_description", "Description"],
] as const;

function VolumeEditor({ volume, docs, onChanged }: { volume: Volume; docs: Doc[]; onChanged: () => void }) {
  const [assign, setAssign] = useState<number[]>([]);
  const save = useMutation({
    mutationFn: (body: Schemas["VolumeUpdate"]) =>
      call(api.PATCH("/volumes/{volume_id}", { params: { path: { volume_id: volume.id } }, body })),
    onSuccess: onChanged,
  });
  const remove = useMutation({
    mutationFn: () => call(api.DELETE("/volumes/{volume_id}", { params: { path: { volume_id: volume.id } } })),
    onSuccess: onChanged,
  });
  const add = useMutation({
    mutationFn: () =>
      call(api.POST("/volumes/{volume_id}/documents", {
        params: { path: { volume_id: volume.id } }, body: { document_ids: assign },
      })),
    onSuccess: () => {
      setAssign([]);
      onChanged();
    },
  });
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    save.mutate(Object.fromEntries(new FormData(e.currentTarget)) as Schemas["VolumeUpdate"]);
  };
  const error = save.error ?? remove.error ?? add.error;
  return (
    <details>
      <summary>{volume.title} <span className="muted">({docs.filter((d) => d.volume_id === volume.id).length} chapters)</span></summary>
      <form className="stack" onSubmit={submit}>
        <label>Title <input name="title" defaultValue={volume.title} required /></label>
        {EPUB_FIELDS.map(([name, label]) => (
          <label key={name}>{label} <input name={name} defaultValue={volume[name]} /></label>
        ))}
        <div className="toolbar">
          <button disabled={save.isPending}>Save</button>
          <button type="button" disabled={remove.isPending} onClick={() => {
            if (window.confirm(`Delete volume "${volume.title}"? Its chapters are kept.`)) remove.mutate();
          }}>Delete volume</button>
        </div>
      </form>
      <div className="toolbar">
        <select multiple aria-label="Chapters to assign" value={assign.map(String)}
          onChange={(e) => setAssign([...e.target.selectedOptions].map((o) => Number(o.value)))}>
          {docs.filter((d) => d.volume_id !== volume.id).map((d) => (
            <option key={d.id} value={d.id}>{d.title}</option>
          ))}
        </select>
        <button disabled={!assign.length || add.isPending} onClick={() => add.mutate()}>Assign to volume</button>
      </div>
      {error && <p className="error" role="alert">{error.message}</p>}
    </details>
  );
}

export default function Volumes({ seriesId, docs }: { seriesId: number; docs: Doc[] }) {
  const queryClient = useQueryClient();
  const key = ["series", seriesId, "volumes"];
  const volumes = useQuery({
    queryKey: key,
    queryFn: () => call(api.GET("/series/{series_id}/volumes", { params: { path: { series_id: seriesId } } })),
  });
  // ["series"] is a prefix of `key`, so this refetches the volumes too.
  const changed = () => invalidateLibrary(queryClient);
  // Generated VolumeCreate marks server-defaulted fields required; the cast sends title only.
  const create = useMutation({
    mutationFn: (title: string) =>
      call(api.POST("/series/{series_id}/volumes", { params: { path: { series_id: seriesId } }, body: { title } as Schemas["VolumeCreate"] })),
    onSuccess: changed,
  });
  if (volumes.isPending) return <p className="muted">Loading volumes…</p>;
  if (volumes.isError) return <p className="error">{volumes.error.message}</p>;
  return (
    <section>
      <div className="toolbar">
        <h2>Volumes</h2>
        <button disabled={create.isPending} onClick={() => {
          const title = window.prompt("Volume title");
          if (title?.trim()) create.mutate(title);
        }}>New volume</button>
      </div>
      {create.isError && <p className="error" role="alert">{create.error.message}</p>}
      {volumes.data.map((v) => <VolumeEditor key={v.id} volume={v} docs={docs} onChanged={changed} />)}
    </section>
  );
}
