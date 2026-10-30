import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api, call } from "../api/client";
import { QUEUE_KEY } from "../jobs/AddToQueueDialog";
import BatchPublish from "../publish/BatchPublish";
import { useAccountPref } from "../settings/useAccountPref";
import { ConfirmDialog, PromptDialog } from "../ui/Dialog";
import Menu from "../ui/Menu";
import ChapterMenu from "./ChapterMenu";
import { cell, cellClass, HEADERS } from "./chapterCells";
import { COLUMNS, DEFAULT_COLUMNS, parseColumns, shownColumns, toggleColumn } from "./chapterColumns";
import { downloadBlob } from "./download";
import MoveDialog from "./MoveDialog";
import { moveItem } from "./order";
import { queuedIds } from "./queuedForOllama";
import { useFlushOllama, useQueueOllama } from "./useOllamaQueue";
import { useWpConfigured } from "../publish/useWpConfigured";
import { shownTitle, type Doc, type SeriesRow } from "./shelf";
import { invalidateLibrary } from "./queries";
import { chapterBlocks, firstOpenBlock, seriesOrder, type VolumeGroup } from "./volumeGroups";
import { CHAPTER_MIME } from "./VolumeList";

const FORMATS = [["txt", "TXT"], ["md", "Markdown"], ["md-ruby", "Ruby Markdown"]] as const;

type Open = null | "publish" | "move" | "merge" | "delete" | "flush";

/** The selected volume's chapters: drag to reorder (native drag events, by the handle), tick rows
 *  for the selection bar, and each row's ⋯ menu. Syosetu series keep syosetu's numbering, so they
 *  have no drag handles. A list over 100 chapters shows as collapsible blocks of 100 (view only),
 *  with a jump bar; only open blocks render. */
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
  const blocks = chapterBlocks({ ...group, docs: shown }, syosetu);
  const [openBlocks, setOpenBlocks] = useState<Set<number>>(() => new Set([blocks[firstOpenBlock(blocks)]?.start ?? 0]));
  const [jumpTo, setJumpTo] = useState<number | null>(null);
  const [chosen, setChosen] = useAccountPref({
    key: "series_columns", local: "ta.seriesColumns", parse: parseColumns, fallback: DEFAULT_COLUMNS,
  });
  const wpConfigured = useWpConfigured() === true;
  const columns = shownColumns(chosen, wpConfigured);
  const queue = useQuery({ queryKey: QUEUE_KEY, queryFn: () => call(api.GET("/ollama/queue")) });
  const queued = queuedIds(queue.data ?? [], shown);
  useEffect(() => {
    if (jumpTo === null) return;
    document.getElementById(`ch-block-${group.key}-${jumpTo}`)?.scrollIntoView({ block: "start" });
    setJumpTo(null);
  }, [jumpTo, group.key]);
  const toggleBlock = (start: number, on: boolean) => {
    const next = new Set(openBlocks);
    if (on) next.add(start);
    else next.delete(start);
    setOpenBlocks(next);
  };
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
  const ollama = useQueueOllama();
  const flush = useFlushOllama(() => setOpen(null));
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
  const row = (d: Doc, i: number) => (
    <tr key={d.id} className={[ticked.has(d.id) && "selected", dragging === d.id && "dragging"].filter(Boolean).join(" ")}
      onDragOver={(e) => { if (dragged.current !== null) e.preventDefault(); }}
      onDrop={(e) => { if (dragged.current !== null) { e.preventDefault(); drop(i); } }}>
      <td className="ch-grip">
        {!syosetu && (
          <span className="grip" draggable title="Drag to reorder" aria-hidden="true"
            onDragStart={(e) => {
              e.dataTransfer.setData(CHAPTER_MIME, String(d.id));
              e.dataTransfer.effectAllowed = "move";
              const tr = e.currentTarget.closest("tr");
              if (tr) e.dataTransfer.setDragImage(tr, 16, 16);
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
      {columns.map((id) => cell(id, { doc: d, group, syosetu, selecting: false, queued }))}
      <td className="ch-menu"><ChapterMenu doc={d} /></td>
    </tr>
  );
  const n = selected.length;
  const error = reorder.error ?? exportZip.error;
  return (
    <>
      {error && <p className="error" role="alert">{error.message}</p>}
      {ollama.error && <p className="error" role="alert">{ollama.error}</p>}
      {ollama.note && <p className="muted" role="status">{ollama.note}</p>}
      {blocks.length > 0 && (
        <nav className="ch-jump" aria-label="Jump to chapters">
          {blocks.map((b) => (
            <button key={b.start} type="button" className="small" aria-pressed={openBlocks.has(b.start)}
              onClick={() => { toggleBlock(b.start, true); setJumpTo(b.start); }}>{b.label}</button>
          ))}
        </nav>
      )}
      {shown.length === 0 ? <p className="muted">No chapters here yet.</p> : (
        <>
          <div className="ch-tools">
            <Menu label="Columns ▾">
              {() => COLUMNS.map((c) => (
                <button key={c.id} type="button" role="menuitemcheckbox" aria-checked={chosen.includes(c.id)}
                  disabled={c.id === "num" || c.id === "title"}
                  onClick={() => setChosen(toggleColumn(chosen, c.id))}>{c.label}</button>
              ))}
            </Menu>
          </div>
          <div className="chapters-wrap">
            <table className="chapters">
              <thead>
                {n > 0 ? (
                  <tr><th colSpan={columns.length + 3}>
                    <div className="selbar">
                      <b>{n} selected</b>
                      <Menu label={exportZip.isPending ? "Exporting…" : "Export ▾"} align="start">
                        {(close) => FORMATS.map(([f, label]) => (
                          <button key={f} type="button" role="menuitem" disabled={exportZip.isPending} onClick={() => { close(); exportZip.mutate(f); }}>{label}</button>
                        ))}
                      </Menu>
                      {wpConfigured && (
                        <button type="button" className="small primary" onClick={() => setOpen("publish")}>Publish…</button>
                      )}
                      <button type="button" className="small" disabled={ollama.pending}
                        onClick={() => ollama.queue({ kind: "documents", series_id: series.id, document_ids: selected })}>Queue for Ollama</button>
                      <button type="button" className="small" onClick={() => { flush.reset(); setOpen("flush"); }}>Flush Ollama output</button>
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
                    {columns.map((id) => <th key={id} className={cellClass(id)}>{HEADERS[id]}</th>)}
                    <th className="ch-menu"><span className="visually-hidden">Actions</span></th>
                  </tr>
                )}
              </thead>
              {blocks.length === 0 ? <tbody>{shown.map(row)}</tbody> : blocks.map((b) => {
                const isOpen = openBlocks.has(b.start);
                return (
                  <tbody key={b.start}>
                    <tr className="ch-block" id={`ch-block-${group.key}-${b.start}`}>
                      <th colSpan={columns.length + 3}>
                        <button type="button" className="quiet" aria-expanded={isOpen} onClick={() => toggleBlock(b.start, !isOpen)}>
                          <span aria-hidden="true">{isOpen ? "▾" : "▸"}</span> {b.label}
                        </button>
                        <span className="muted">{b.docs.length} chapters · {b.progress}%</span>
                      </th>
                    </tr>
                    {isOpen && b.docs.map((d, i) => row(d, b.start + i))}
                  </tbody>
                );
              })}
            </table>
          </div>
        </>
      )}
      {open === "flush" && (
        <ConfirmDialog title="Flush Ollama output" confirmLabel="Flush" danger busy={flush.pending}
          message={`Clear Ollama's saved suggestions for ${n} ${n === 1 ? "chapter" : "chapters"}? Your own translation is not touched.`}
          error={flush.error} onConfirm={() => flush.flush({ document_ids: selected })} onClose={() => setOpen(null)} />
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
