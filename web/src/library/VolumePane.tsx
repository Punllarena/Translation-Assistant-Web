import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, call } from "../api/client";
import BatchPublish from "../publish/BatchPublish";
import { ConfirmDialog } from "../ui/Dialog";
import Menu from "../ui/Menu";
import { downloadBlob } from "./download";
import NewDocument from "./NewDocument";
import type { SeriesRow } from "./shelf";
import { invalidateLibrary } from "./queries";
import VolumeDetails, { Illustrations, useIllustrations } from "./VolumeDetails";
import { groupTitle, VolumeCover } from "./VolumeList";
import type { VolumeGroup } from "./volumeGroups";

type Open = null | "publish" | "details" | "illustrations" | "delete" | "chapter" | "renumber";

function editedLabel(group: VolumeGroup): string | null {
  let at: string | null = null;
  for (const d of group.docs) if (at === null || d.updated_at > at) at = d.updated_at;
  return at && new Date(at).toLocaleDateString();
}

/** The selected volume's header: cover, title, counts and the volume-level actions. The "No volume"
 *  group only offers New chapter (and New volume when the series has none yet). */
export default function VolumePane({ series, group, syosetu, hasVolumes, onNewVolume, kinds }: {
  series: SeriesRow; group: VolumeGroup; syosetu: boolean; hasVolumes: boolean; onNewVolume: () => void;
  kinds: string[];
}) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState<Open>(null);
  const volume = group.volume;
  const changed = () => invalidateLibrary(queryClient);
  const illustrations = useIllustrations(volume);
  const epub = useMutation({
    mutationFn: () => downloadBlob(`/api/volumes/${volume!.id}/export/epub`, `${volume!.full_title}.epub`),
  });
  const renumber = useMutation({
    mutationFn: () => call(api.POST("/series/{series_id}/renumber", { params: { path: { series_id: series.id } } })),
    onSettled: changed,
    onSuccess: () => setOpen((o) => (o === "renumber" ? null : o)),
  });
  const remove = useMutation({
    mutationFn: () => call(api.DELETE("/volumes/{volume_id}", { params: { path: { volume_id: volume!.id } } })),
    onSuccess: async () => { await changed(); setOpen(null); },
  });
  const count = group.docs.length;
  const edited = editedLabel(group);
  const meta = [`${count} ${count === 1 ? "chapter" : "chapters"}`, `${group.progress}% translated`, edited && `edited ${edited}`]
    .filter(Boolean).join(" · ");
  const markdown = (variant: string) =>
    `/api/series/${series.id}/export/markdown?variant=${variant}&volume_id=${volume?.id}`;
  const newChapter = <button type="button" onClick={() => setOpen("chapter")}>New chapter</button>;
  const renumberButton = !syosetu && (
    <button type="button" disabled={renumber.isPending} onClick={() => renumber.mutate()}>Renumber by title</button>
  );
  const error = epub.error ?? (open === "renumber" ? null : renumber.error);
  return (
    <div className={volume ? "vol-head" : "vol-head loose"}>
      {volume && <VolumeCover group={group} />}
      <div className="vol-head-main">
        <h2 className="vol-head-title">{hasVolumes ? groupTitle(group) : "Chapters"}</h2>
        <p className="muted">{meta}</p>
        <div className="toolbar">
          {volume ? (
            <>
              <button type="button" className="primary" disabled={count === 0} onClick={() => setOpen("publish")}>Publish volume…</button>
              <Menu label="Export volume ▾" align="start">
                {(close) => (
                  <>
                    <button type="button" role="menuitem" disabled={epub.isPending}
                      onClick={() => { close(); epub.mutate(); }}>{epub.isPending ? "Building EPUB…" : "EPUB"}</button>
                    <a role="menuitem" className="btn" href={markdown("plain")} download onClick={close}>Markdown ZIP (complete chapters only)</a>
                    <a role="menuitem" className="btn" href={markdown("ruby")} download onClick={close}>Ruby Markdown ZIP (complete chapters only)</a>
                  </>
                )}
              </Menu>
              {newChapter}
              <Menu label="⋯" buttonLabel="Volume actions">
                {(close) => (
                  <>
                    <button type="button" role="menuitem" onClick={() => { close(); setOpen("details"); }}>Edit volume details</button>
                    <button type="button" role="menuitem" disabled={illustrations.running}
                      onClick={() => { close(); setOpen("illustrations"); }}>Publish illustrations</button>
                    {!syosetu && (
                      <button type="button" role="menuitem"
                        onClick={() => { close(); renumber.reset(); setOpen("renumber"); }}>Renumber all volumes by title</button>
                    )}
                    <button type="button" role="menuitem" className="danger"
                      onClick={() => { close(); remove.reset(); setOpen("delete"); }}>Delete volume</button>
                  </>
                )}
              </Menu>
            </>
          ) : (
            <>
              {newChapter}
              {!hasVolumes && <button type="button" onClick={onNewVolume}>New volume</button>}
              {!hasVolumes && renumberButton}
            </>
          )}
        </div>
        {error && <p className="error" role="alert">{error.message}</p>}
        {volume && <Illustrations volume={volume} job={illustrations} asking={open === "illustrations"} onAsked={() => setOpen(null)} />}
      </div>
      {open === "publish" && <BatchPublish ids={group.docs.map((d) => d.id)} onClose={() => setOpen(null)} />}
      {open === "details" && volume && <VolumeDetails volume={volume} series={series} kinds={kinds} onClose={() => setOpen(null)} />}
      {open === "delete" && volume && (
        <ConfirmDialog title="Delete volume" confirmLabel="Delete volume" danger busy={remove.isPending}
          message={`Delete volume "${volume.label}"? Its chapters stay in the series.`} error={remove.error?.message}
          onConfirm={() => remove.mutate()} onClose={() => setOpen(null)} />
      )}
      {open === "renumber" && (
        <ConfirmDialog title="Renumber by title" confirmLabel="Renumber" busy={renumber.isPending}
          message="Renumber every chapter in this series by title? Each volume is sorted by chapter title."
          error={renumber.error?.message} onConfirm={() => renumber.mutate()} onClose={() => setOpen(null)} />
      )}
      {open === "chapter" && (
        <NewDocument seriesId={series.id} volumeId={volume?.id ?? null} onClose={() => setOpen(null)} />
      )}
    </div>
  );
}
