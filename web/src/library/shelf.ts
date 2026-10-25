import type { Schemas } from "../api/client";

export type Doc = Schemas["DocumentListItem"];
export type SeriesRow = Schemas["SeriesOut"];
export type Volume = Schemas["VolumeOut"];

export interface SeriesCard {
  series: SeriesRow;
  coverImageId: number | null;
  volumeCount: number;
  chapterCount: number;
  progress: number;
  editedAt: string | null;
  /** Newest chapter created_at. */
  addedAt: string | null;
  /** Newest chapter wp_published_at. */
  publishedAt: string | null;
  /** At least one chapter is live on WordPress. */
  hasPublished: boolean;
}

export const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });

export const byVolumeOrder = (a: Volume, b: Volume) => a.volume_order - b.volume_order || a.id - b.id;
type Titled = Pick<Doc, "title" | "chapter_title">;
/** The title a chapter shows, as the desktop does: its chapter_title (where a translated title lives), else its own name. */
export const shownTitle = (d: Titled) => d.chapter_title || d.title;
/** The field Rename writes: the one shownTitle reads. */
export const titleField = (d: Titled): "chapter_title" | "title" => (d.chapter_title ? "chapter_title" : "title");
export const bySeriesOrder =(a: Doc, b: Doc) => a.series_order - b.series_order || a.id - b.id;

/** Σtranslated·100 / Σlines, floored; 0 when there are no lines. */
export function progressOf(docs: Doc[]): number {
  let lines = 0;
  let done = 0;
  for (const d of docs) {
    lines += d.line_count;
    done += d.translated_count;
  }
  return lines > 0 ? Math.floor((done * 100) / lines) : 0;
}

/** The series cover: the chosen volume's cover, else the first volume's (in order) that has one.
 *  `vols` must be in volume order. */
export function seriesCover(vols: Volume[]): number | null {
  const chosen = vols.find((v) => v.is_series_cover)?.cover_id;
  return chosen ?? vols.find((v) => v.cover_id != null)?.cover_id ?? null;
}

const later = (a: string | null, b: string | null) => (b !== null && (a === null || b > a) ? b : a);

export function seriesCards(series: SeriesRow[], docs: Doc[], volumes: Volume[]): SeriesCard[] {
  return series.map((s) => {
    const own = docs.filter((d) => d.series_id === s.id).sort(bySeriesOrder);
    const vols = volumes.filter((v) => v.series_id === s.id).sort(byVolumeOrder);
    let editedAt: string | null = null;
    let addedAt: string | null = null;
    let publishedAt: string | null = null;
    for (const d of own) {
      editedAt = later(editedAt, d.updated_at);
      addedAt = later(addedAt, d.created_at);
      publishedAt = later(publishedAt, d.wp_published_at ?? null);
    }
    return {
      series: s,
      coverImageId: seriesCover(vols),
      volumeCount: vols.length,
      chapterCount: own.length,
      progress: progressOf(own),
      editedAt,
      addedAt,
      publishedAt,
      hasPublished: own.some((d) => d.wp_status === "publish"),
    };
  });
}

export function sizeLabel(card: SeriesCard): string {
  const ch = `${card.chapterCount} ch`;
  if (card.volumeCount === 0) return ch;
  return `${card.volumeCount} ${card.volumeCount === 1 ? "vol" : "vols"} · ${ch}`;
}
