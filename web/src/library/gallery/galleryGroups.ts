import type { Schemas } from "../../api/client";
import { bySeriesOrder, byVolumeOrder, shownTitle, type Doc, type Volume } from "../shelf";

export type GalleryImage = Schemas["GalleryImageOut"];

export interface GalleryChapter {
  doc: Doc;
  /** "Ch. 3 · Title", or the title alone for a chapter with no number (the Illustrations one). */
  heading: string;
  images: GalleryImage[];
}

export interface GalleryVolume {
  key: string;
  label: string;
  cover: GalleryImage | null;
  chapters: GalleryChapter[];
}

export const imageKey = (image: GalleryImage) => `${image.kind}-${image.id}`;

export const imageSrc = (image: GalleryImage) =>
  image.kind === "cover" ? `/api/covers/${image.id}` : `/api/images/${image.id}`;

const heading = (doc: Doc) =>
  doc.chapter_number == null ? shownTitle(doc) : `Ch. ${doc.chapter_number} · ${shownTitle(doc)}`;

/** The series' images grouped by volume (in volume order, "No volume" last), the cover first,
 *  then chapters by order with each chapter's images by anchor. A group with neither a cover
 *  nor an image is left out. `filter` keeps one volume only. */
export function galleryGroups(
  images: GalleryImage[],
  docs: Doc[],
  volumes: Volume[],
  filter: number | "all" = "all",
): GalleryVolume[] {
  const known = new Set(volumes.map((v) => v.id));
  const byDoc = new Map<number, GalleryImage[]>();
  for (const image of images) {
    if (image.kind !== "image" || image.document_id == null) continue;
    const list = byDoc.get(image.document_id) ?? [];
    list.push(image);
    byDoc.set(image.document_id, list);
  }
  const group = (key: string, label: string, volumeId: number | null): GalleryVolume => {
    const own =
      volumeId === null
        ? docs.filter((d) => d.volume_id == null || !known.has(d.volume_id))
        : docs.filter((d) => d.volume_id === volumeId);
    return {
      key,
      label,
      cover: volumeId === null
        ? null
        : images.find((i) => i.kind === "cover" && i.volume_id === volumeId) ?? null,
      chapters: own
        .filter((d) => byDoc.has(d.id))
        .sort(bySeriesOrder)
        .map((doc) => ({
          doc,
          heading: heading(doc),
          images: [...(byDoc.get(doc.id) ?? [])].sort(
            (a, b) => a.anchor_position - b.anchor_position || a.id - b.id,
          ),
        })),
    };
  };
  const groups = volumes
    .filter((v) => filter === "all" || v.id === filter)
    .sort(byVolumeOrder)
    .map((v) => group(`v${v.id}`, v.label, v.id));
  if (filter === "all") {
    const loose = group("none", "No volume", null);
    if (loose.chapters.length > 0) groups.push(loose);
  }
  return groups.filter((g) => g.cover !== null || g.chapters.length > 0);
}

/** Every image in display order, for the viewer's previous/next. */
export function flatten(groups: GalleryVolume[]): GalleryImage[] {
  return groups.flatMap((g) => [
    ...(g.cover ? [g.cover] : []),
    ...g.chapters.flatMap((c) => c.images),
  ]);
}

/** What the viewer offers for an image. Any chapter image can be deleted; only one in a volume can
 *  become its cover or move (and not from the Illustrations chapter or in a syosetu series). Cover
 *  tiles are view only. */
export function imageActions(image: GalleryImage, doc: Doc | undefined, syosetu: boolean) {
  const chapterImage = image.kind === "image";
  const cover = chapterImage && image.volume_id != null;
  return { cover, move: cover && !syosetu && doc?.is_illustrations !== true, remove: chapterImage };
}
