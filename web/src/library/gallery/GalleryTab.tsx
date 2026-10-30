import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { api, call } from "../../api/client";
import { useAllVolumes } from "../queries";
import type { Doc, SeriesRow } from "../shelf";
import {
  flatten, galleryGroups, imageKey, imageSrc, type GalleryImage, type GalleryVolume,
} from "./galleryGroups";
import ImageViewer from "./ImageViewer";

function Tile({ image, onOpen }: { image: GalleryImage; onOpen: () => void }) {
  return (
    <button type="button" className="gallery-tile" onClick={onOpen}
      aria-label={`${image.kind === "cover" ? "View cover" : "View"} ${image.src_path}`}>
      <img src={imageSrc(image)} alt={image.src_path} loading="lazy" decoding="async" />
    </button>
  );
}

function Group({ group, onOpen }: { group: GalleryVolume; onOpen: (image: GalleryImage) => void }) {
  const cover = group.cover;
  return (
    <section className="gallery-group" aria-label={group.label}>
      <h2>{group.label}</h2>
      {cover && (
        <div className="gallery-grid">
          <Tile image={cover} onOpen={() => onOpen(cover)} />
        </div>
      )}
      {group.chapters.map((chapter) => (
        <div key={chapter.doc.id} className="gallery-chapter">
          <h3>{chapter.heading}</h3>
          <div className="gallery-grid">
            {chapter.images.map((image) => (
              <Tile key={imageKey(image)} image={image} onOpen={() => onOpen(image)} />
            ))}
          </div>
        </div>
      ))}
    </section>
  );
}

/** The series page's Gallery tab: every image of the series (volume covers first) with a
 *  volume filter; a tile opens the full-size viewer. Nothing here links to the editor. */
export default function GalleryTab({ series, docs }: { series: SeriesRow; docs: Doc[] }) {
  const volumes = useAllVolumes();
  const [filter, setFilter] = useState<number | "all">("all");
  const [openKey, setOpenKey] = useState<string | null>(null);
  const gallery = useQuery({
    queryKey: ["gallery", series.id],
    queryFn: () => call(api.GET("/series/{series_id}/images", {
      params: { path: { series_id: series.id } },
    })),
  });
  const vols = useMemo(
    () => (volumes.data ?? []).filter((v) => v.series_id === series.id),
    [volumes.data, series.id],
  );
  // A filter on a volume that has since gone falls back to All (its chapters are loose now).
  useEffect(() => {
    if (filter !== "all" && vols.length > 0 && !vols.some((v) => v.id === filter)) setFilter("all");
  }, [filter, vols]);
  const groups = useMemo(
    () => galleryGroups(gallery.data ?? [], docs, vols, filter),
    [gallery.data, docs, vols, filter],
  );
  const flat = useMemo(() => flatten(groups), [groups]);
  const index = flat.findIndex((image) => imageKey(image) === openKey);
  const image = index >= 0 ? flat[index] : null;
  const doc = image?.document_id != null ? docs.find((d) => d.id === image.document_id) : undefined;
  if (gallery.isPending) return <p className="muted">Loading images…</p>;
  if (gallery.isError) return <p className="error" role="alert">{gallery.error.message}</p>;
  return (
    <>
      {vols.length > 0 && (
        <label className="gallery-filter">
          <span>Volume</span>
          <select value={String(filter)}
            onChange={(e) => setFilter(e.target.value === "all" ? "all" : Number(e.target.value))}>
            <option value="all">All</option>
            {vols.map((v) => <option key={v.id} value={v.id}>{v.label}</option>)}
          </select>
        </label>
      )}
      {flat.length === 0 && <p className="muted">No images in this series yet.</p>}
      {groups.map((group) => (
        <Group key={group.key} group={group}
          onOpen={(picked) => setOpenKey(imageKey(picked))} />
      ))}
      {image && (
        <ImageViewer image={image} doc={doc} seriesId={series.id}
          syosetu={series.syosetu_url.trim() !== ""} images={flat} index={index}
          onStep={(delta) => {
            const next = flat[index + delta];
            if (next) setOpenKey(imageKey(next));
          }}
          onClose={() => setOpenKey(null)} />
      )}
    </>
  );
}
