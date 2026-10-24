import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { Link } from "react-router";
import { api, call } from "../api/client";
import BatchPublish from "../publish/BatchPublish";
import { wpBadge } from "../publish/badge";
import { statusTone } from "../publish/label";
import { ConfirmDialog, PromptDialog } from "../ui/Dialog";
import Menu from "../ui/Menu";
import ChapterMenu from "./ChapterMenu";
import { downloadBlob } from "./download";
import MoveDialog from "./MoveDialog";
import { moveItem } from "./order";
import { shownTitle, type Doc, type SeriesRow } from "./shelf";
import { invalidateLibrary } from "./queries";
import { chapterNumber, seriesOrder, type VolumeGroup } from "./volumeGroups";
import { CHAPTER_MIME } from "./VolumeList";

const WP_LABEL: Record<string, string> = { publish: "Published", future: "Scheduled" };
const FORMATS = [["txt", "TXT"], ["md", "Markdown"], ["md-ruby", "Ruby Markdown"]] as const;

type Open = null | "publish" | "move" | "merge" | "delete";

/** The selected volume's chapters: drag to reorder (native drag events, by the handle), tick rows
 *  for the selection bar, and each row's ⋯ menu. Syosetu series keep syosetu's numbering, so they
 *  have no drag handles. */
export default function ChapterTable({ series, group, groups, syosetu }: {
  series: SeriesRow; group: VolumeGroup; groups: VolumeGroup[]; syosetu: boolean;
}) {
  const queryClient = useQueryClient();
  const [ticked, setTicked] = useState<Set<number>>(new Set());
  const [open, setOpen] = useState<Open>(null);
  const [dragging, setDragging] = useState<number | null>(null); // styling only
  const dragged = useRef<number | null>(null); // read by the drop handlers, set before any re-render
  const [order, setOrder] = useState<Doc[] | null>(null); // optimistic order while saving
  const shown = order ?? group.docs;
  const selected = group.docs.filter((d) => ticked.has(d.id)).map((d) => d.id);
  const clear = () => setTicked(new Set());
  const done = async () => { await invalidateLibrary(queryClient); clear(); setOpen(null); };
  const reorder = useMutation({
    mutationFn: (ids: number[]) =>
      call(api.PUT("/series/{series_id}/order", { params: { path: { series_id: series.id } }, body: { document_ids: ids } })),
    onSettled: async () => { await invalidateLibrary(queryClient); setOrder(null); },
  });
  const merge = useMutation({
    mutationFn: (title: string) => call(api.POST("/documents/merge", { body: { document_ids: selected, title } })),
    onSuccess: done,
  });
  const remove = useMutation({
    mutationFn: async () => {
      for (const id of selected) await call(api.DELETE("/documents/{document_id}", { params: { path: { document_id: id } } }));
    },
    onSettled: () => invalidateLibrary(queryClient), // a partial failure still changed the list
    onSuccess: () => { clear(); setOpen(null); },
  });
  const exportZip = useMutation({
    mutationFn: (format: string) => downloadBlob("/api/documents/export/zip", "chapters.zip", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ document_ids: selected, format }),
    }),
  });
  const toggle = (id: number, on: boolean) => {
    const next = new Set(ticked);
    if (on) next.add(id);
    else next.delete(id);
    setTicked(next);
  };
  const endDrag = () => { dragged.current = null; setDragging(null); };
  const drop = (to: number) => {
    const from = shown.findIndex((d) => d.id === dragged.current);
    endDrag();
    if (from < 0 || from === to) return;
    const next = moveItem(shown, from, to);
    setOrder(next);
    reorder.mutate(seriesOrder(groups, group.key, next));
  };
  const n = selected.length;
  const error = reorder.error ?? exportZip.error;
  return (
    <>
      {error && <p className="error" role="alert">{error.message}</p>}
      {shown.length === 0 ? <p className="muted">No chapters here yet.</p> : (
        <table className="chapters">
          <thead>
            {n > 0 ? (
              <tr><th colSpan={8}>
                <div className="selbar">
                  <b>{n} selected</b>
                  <Menu label={exportZip.isPending ? "Exporting…" : "Export ▾"} align="start">
                    {(close) => FORMATS.map(([f, label]) => (
                      <button key={f} type="button" role="menuitem" disabled={exportZip.isPending} onClick={() => { close(); exportZip.mutate(f); }}>{label}</button>
                    ))}
                  </Menu>
                  <button type="button" className="small primary" onClick={() => setOpen("publish")}>Publish…</button>
                  <button type="button" className="small" onClick={() => setOpen("move")}>Move to…</button>
                  <button type="button" className="small" disabled={n < 2} onClick={() => { merge.reset(); setOpen("merge"); }}>Merge</button>
                  <button type="button" className="small danger" onClick={() => { remove.reset(); setOpen("delete"); }}>Delete</button>
                  <span className="spacer" />
                  <button type="button" className="small quiet" onClick={clear}>Clear</button>
                </div>
              </th></tr>
            ) : (
              <tr>
                <th className="ch-grip"><span className="visually-hidden">Drag</span></th>
                <th className="ch-check"><span className="visually-hidden">Select</span></th>
                <th className="ch-num">#</th>
                <th>Chapter</th>
                <th className="ch-prog">Progress</th>
                <th className="ch-edited">Edited</th>
                <th className="ch-wp">WordPress</th>
                <th className="ch-menu"><span className="visually-hidden">Actions</span></th>
              </tr>
            )}
          </thead>
          <tbody>
            {shown.map((d, i) => (
              <tr key={d.id} className={[ticked.has(d.id) && "selected", dragging === d.id && "dragging"].filter(Boolean).join(" ")}
                onDragOver={(e) => { if (dragged.current !== null) e.preventDefault(); }}
                onDrop={(e) => { if (dragged.current !== null) { e.preventDefault(); drop(i); } }}>
                <td className="ch-grip">
                  {!syosetu && (
                    <span className="grip" draggable title="Drag to reorder" aria-hidden="true"
                      onDragStart={(e) => {
                        e.dataTransfer.setData(CHAPTER_MIME, String(d.id));
                        e.dataTransfer.effectAllowed = "move";
                        const row = e.currentTarget.closest("tr");
                        if (row) e.dataTransfer.setDragImage(row, 16, 16);
                        dragged.current = d.id;
                        // Chrome cancels a drag whose source is re-rendered inside dragstart.
                        setTimeout(() => { if (dragged.current === d.id) setDragging(d.id); });
                      }}
                      onDragEnd={endDrag}>⠿</span>
                  )}
                </td>
                <td className="ch-check">
                  <input type="checkbox" aria-label={`Select ${shownTitle(d)}`} checked={ticked.has(d.id)}
                    onChange={(e) => toggle(d.id, e.target.checked)} />
                </td>
                <td className="ch-num muted">{chapterNumber(group, d, syosetu) ?? ""}</td>
                <td className="ch-title">
                  <Link className="row-link" to={`/documents/${d.id}`} aria-label={`Open ${shownTitle(d)}`}>{shownTitle(d)}</Link>
                </td>
                <td className={d.progress >= 100 ? "ch-prog ok" : "ch-prog"}>{d.progress}%</td>
                <td className="ch-edited muted">{new Date(d.updated_at).toLocaleDateString()}</td>
                <td className="ch-wp">
                  <span className={`badge ${statusTone(d.wp_status)}`} title={wpBadge(d) || undefined}>
                    {WP_LABEL[d.wp_status] ?? "Not posted"}
                  </span>
                </td>
                <td className="ch-menu"><ChapterMenu doc={d} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {open === "publish" && <BatchPublish ids={selected} onClose={() => setOpen(null)} />}
      {open === "move" && (
        <MoveDialog ids={selected} currentSeriesId={series.id}
          currentVolumeId={group.volume?.id ?? null} onMoved={clear} onClose={() => setOpen(null)} />
      )}
      {open === "merge" && (
        <PromptDialog title={`Merge ${n} chapters`} confirmLabel="Merge" busy={merge.isPending}
          label="Chapter heading for the merged chapter (it keeps the first chapter's name)"
          error={merge.error?.message} onSubmit={(t) => merge.mutate(t.trim())} onClose={() => setOpen(null)} />
      )}
      {open === "delete" && (
        <ConfirmDialog title="Delete chapters" confirmLabel="Delete" danger busy={remove.isPending}
          message={`Delete ${n} ${n === 1 ? "chapter" : "chapters"}? This can't be undone.`}
          error={remove.error?.message} onConfirm={() => remove.mutate()} onClose={() => setOpen(null)} />
      )}
    </>
  );
}
