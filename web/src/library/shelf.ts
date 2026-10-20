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
}

const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });

export const byVolumeOrder = (a: Volume, b: Volume) => a.volume_order - b.volume_order || a.id - b.id;
export const bySeriesOrder = (a: Doc, b: Doc) => a.series_order - b.series_order || a.id - b.id;

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

export const firstCover = (docs: Doc[]): number | null => docs.find((d) => d.cover_image_id != null)?.cover_image_id ?? null;

export function seriesCards(series: SeriesRow[], docs: Doc[], volumes: Volume[], filter: string): SeriesCard[] {
  const needle = filter.trim().toLowerCase();
  return series
    .filter((s) => !needle || s.title.toLowerCase().includes(needle))
    .sort((a, b) => collator.compare(a.title, b.title))
    .map((s) => {
      const own = docs.filter((d) => d.series_id === s.id).sort(bySeriesOrder);
      const vols = volumes.filter((v) => v.series_id === s.id).sort(byVolumeOrder);
      const first = vols[0];
      const cover = (first && firstCover(own.filter((d) => d.volume_id === first.id))) ?? firstCover(own);
      let editedAt: string | null = null;
      for (const d of own) if (editedAt === null || d.updated_at > editedAt) editedAt = d.updated_at;
      return {
        series: s,
        coverImageId: cover,
        volumeCount: vols.length,
        chapterCount: own.length,
        progress: progressOf(own),
        editedAt,
      };
    });
}

export function sizeLabel(card: SeriesCard): string {
  const ch = `${card.chapterCount} ch`;
  if (card.volumeCount === 0) return ch;
  return `${card.volumeCount} ${card.volumeCount === 1 ? "vol" : "vols"} · ${ch}`;
}
