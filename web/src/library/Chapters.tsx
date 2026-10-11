import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, ApiError, call, errorMessage } from "../api/client";
import type { Doc } from "./group";
import { moveItem } from "./order";
import { invalidateLibrary } from "./queries";

/** A series' chapters in reading order: drag to reorder (native drag events), renumber by
 *  title, and set or clear each chapter's cover. Keyboard users cannot drag rows;
 *  "Renumber by title" is the keyboard path for ordering. */
export default function Chapters({ seriesId, docs }: { seriesId: number; docs: Doc[] }) {
  const queryClient = useQueryClient();
  const [dragging, setDragging] = useState<number | null>(null);
  const [order, setOrder] = useState<Doc[] | null>(null); // optimistic order while saving
  const shown = order ?? docs;
  const settle = async () => {
    await invalidateLibrary(queryClient);
    setOrder(null);
  };
  const reorder = useMutation({
    mutationFn: (ids: number[]) =>
      call(api.PUT("/series/{series_id}/order", {
        params: { path: { series_id: seriesId } }, body: { document_ids: ids },
      })),
    onSettled: settle,
  });
  const renumber = useMutation({
    mutationFn: () =>
      call(api.POST("/series/{series_id}/renumber", { params: { path: { series_id: seriesId } } })),
    onSettled: settle,
  });
  const cover = useMutation({
    mutationFn: async ({ id, file }: { id: number; file: File | null }) => {
      if (!file) {
        return call(api.DELETE("/documents/{document_id}/cover", { params: { path: { document_id: id } } }));
      }
      const form = new FormData();
      form.append("file", file);
      const response = await fetch(`/api/documents/${id}/cover`, { method: "PUT", body: form });
      if (!response.ok) {
        throw new ApiError(response.status, errorMessage(await response.json().catch(() => null)));
      }
    },
    onSettled: settle,
  });
  const drop = (to: number) => {
    if (dragging === null || dragging === to) return;
    const next = moveItem(shown, dragging, to);
    setOrder(next);
    setDragging(null);
    reorder.mutate(next.map((d) => d.id));
  };
  const error = reorder.error ?? renumber.error ?? cover.error;
  return (
    <section>
      <div className="toolbar">
        <h2>Chapters</h2>
        <button onClick={() => renumber.mutate()} disabled={renumber.isPending}>Renumber by title</button>
      </div>
      {error && <p className="error" role="alert">{error.message}</p>}
      <table>
        <tbody>
          {shown.map((d, i) => (
            <tr key={d.id} draggable onDragStart={(e) => {
                e.dataTransfer.setData("text/plain", String(d.id));
                e.dataTransfer.effectAllowed = "move";
                setDragging(i);
              }}
              onDragEnd={() => setDragging(null)}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                if (dragging !== null) drop(i);
              }}>
              <td aria-hidden>⠿</td>
              <td>{d.title}</td>
              <td>{d.progress}%</td>
              <td>
                {d.has_cover ? "Cover set " : ""}
                <label>
                  {d.has_cover ? "Replace" : "Set cover"}{" "}
                  <input type="file" accept="image/png,image/jpeg,image/gif,image/webp"
                    disabled={cover.isPending}
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      e.target.value = "";
                      if (file) cover.mutate({ id: d.id, file });
                    }} />
                </label>
                {d.has_cover && (
                  <button disabled={cover.isPending} onClick={() => cover.mutate({ id: d.id, file: null })}>Clear</button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
