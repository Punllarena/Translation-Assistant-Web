import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useSearchParams } from "react-router";
import { api, call } from "../api/client";
import { ConfirmDialog } from "../ui/Dialog";
import ChapterTable from "./ChapterTable";
import type { Doc, SeriesRow } from "./shelf";
import { invalidateLibrary, useAllVolumes } from "./queries";
import MergeVolumesDialog from "./MergeVolumesDialog";
import NewVolumeDialog from "./NewVolumeDialog";
import { moveItem } from "./order";
import { kindOptions } from "./VolumeNameFields";
import { pickedInOrder, rangeToggle } from "./rangeToggle";
import { useFlushOllama, useQueueOllama } from "./useOllamaQueue";
import VolumeList from "./VolumeList";
import VolumePane from "./VolumePane";
import { pickVolume, volumeGroups, type VolumeKey } from "./volumeGroups";

/** The series page's Volumes tab: volumes on the left (¼), the selected one's chapters on the right.
 *  The selected volume lives in the `volume` URL param. */
export default function VolumesTab({ series, docs }: { series: SeriesRow; docs: Doc[] }) {
  const queryClient = useQueryClient();
  const volumes = useAllVolumes();
  const [params, setParams] = useSearchParams();
  const [creating, setCreating] = useState(false);
  const [selecting, setSelecting] = useState(false);
  const [picked, setPicked] = useState<Set<number>>(new Set());
  const [anchor, setAnchor] = useState<number | null>(null);
  const [merging, setMerging] = useState(false);
  const ollama = useQueueOllama();
  const [flushing, setFlushing] = useState(false);
  const flush = useFlushOllama(() => setFlushing(false));
  const groups = useMemo(() => volumeGroups(series.id, docs, volumes.data ?? []), [series.id, docs, volumes.data]);
  const syosetu = series.syosetu_url.trim() !== "";
  const hasVolumes = groups.some((g) => g.volume !== null);
  const selected = pickVolume(params.get("volume"), groups);
  const group = groups.find((g) => g.key === selected) ?? groups[0];
  const select = (key: VolumeKey) => {
    const next = new URLSearchParams(params);
    next.set("volume", String(key));
    setParams(next, { replace: true });
  };
  // Dropping a chapter on a volume entry: it goes to the end of that volume.
  const assign = useMutation({
    mutationFn: async ({ docId, key }: { docId: number; key: VolumeKey }) => {
      if (key === "none") {
        await call(api.PATCH("/documents/{document_id}", { params: { path: { document_id: docId } }, body: { volume_id: null } }));
      } else {
        await call(api.POST("/volumes/{volume_id}/documents", { params: { path: { volume_id: key } }, body: { document_ids: [docId] } }));
      }
    },
    onSettled: () => invalidateLibrary(queryClient),
  });
  const dropChapter = (docId: number, key: VolumeKey) => {
    const from = groups.find((g) => g.docs.some((d) => d.id === docId));
    if (from && from.key !== key) assign.mutate({ docId, key });
  };
  // Dragging a volume onto another puts it at that volume's place; the API answers with the new order.
  const reorder = useMutation({
    mutationFn: (ids: number[]) =>
      call(api.PUT("/series/{series_id}/volumes/order", { params: { path: { series_id: series.id } }, body: { volume_ids: ids } })),
    onSettled: () => invalidateLibrary(queryClient),
  });
  if (volumes.isPending) return <p className="muted">Loading volumes…</p>;
  if (volumes.isError) return <p className="error" role="alert">{volumes.error.message}</p>;
  const newVolume = () => setCreating(true);
  const allVolumes = groups.flatMap((g) => (g.volume ? [g.volume] : []));
  const kinds = kindOptions(allVolumes);
  const moveVolume = (fromId: number, toId: number) => {
    const ids = allVolumes.map((v) => v.id);
    const from = ids.indexOf(fromId), to = ids.indexOf(toId);
    if (from >= 0 && to >= 0 && from !== to) reorder.mutate(moveItem(ids, from, to));
  };
  const order = groups.flatMap((g) => (g.volume ? [g.volume.id] : []));
  const leaveSelecting = () => { setSelecting(false); setPicked(new Set()); setAnchor(null); };
  const pick = (id: number, shift: boolean) => { setPicked((p) => rangeToggle(order, p, id, anchor, shift)); setAnchor(id); };
  const live = new Set(pickedInOrder(order, picked));
  const pickedVolumes = groups.flatMap((g) => (g.volume && live.has(g.volume.id) ? [g.volume] : []));
  return (
    <>
      <div className="toolbar">
        <button type="button" disabled={ollama.pending || docs.length === 0}
          onClick={() => ollama.queue({ kind: "series", series_id: series.id })}>Queue series for Ollama</button>
        <button type="button" onClick={() => { flush.reset(); setFlushing(true); }}>Flush Ollama output…</button>
        {ollama.note && <span className="muted" role="status">{ollama.note}</span>}
        {ollama.error && <span className="error" role="alert">{ollama.error}</span>}
      </div>
      <div className={hasVolumes ? "vol-panes" : "vol-panes single"}>
        {hasVolumes && (
          <VolumeList groups={groups} selected={group.key} onSelect={select} onNewVolume={newVolume} onDropChapter={dropChapter} onMoveVolume={moveVolume}
            selecting={selecting} picked={live} onPick={pick} onMerge={() => setMerging(true)}
            onToggleSelecting={() => (selecting ? leaveSelecting() : setSelecting(true))} />
        )}
        <section className="vol-pane" aria-label={group.volume?.label ?? "Chapters"}>
          <VolumePane key={`head-${group.key}`} series={series} group={group} syosetu={syosetu} hasVolumes={hasVolumes}
            onNewVolume={newVolume} kinds={kinds} />
          {reorder.isError && <p className="error" role="alert">{reorder.error.message}</p>}
          {assign.isError && <p className="error" role="alert">{assign.error.message}</p>}
          <ChapterTable key={`table-${group.key}`} series={series} group={group} groups={groups} syosetu={syosetu} />
        </section>
        {flushing && (
          <ConfirmDialog title="Flush Ollama output" confirmLabel="Flush" danger busy={flush.pending}
            message="Clear Ollama's saved suggestions for every chapter in this series? Your own translation is not touched."
            error={flush.error} onConfirm={() => flush.flush({ series_id: series.id })} onClose={() => setFlushing(false)} />
        )}
        {merging && pickedVolumes.length >= 2 && (
          <MergeVolumesDialog seriesId={series.id} volumes={pickedVolumes} onClose={() => setMerging(false)}
            onMerged={(id) => { setMerging(false); leaveSelecting(); select(id); }} />
        )}
        {creating && (
          <NewVolumeDialog series={series} volumes={allVolumes} onClose={() => setCreating(false)}
            onCreated={(id) => { setCreating(false); select(id); }} />
        )}
      </div>
    </>
  );
}
