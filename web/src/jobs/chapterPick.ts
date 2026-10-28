import type { Doc, Volume } from "../library/shelf";
import { chapterNumber, volumeGroups, type VolumeKey } from "../library/volumeGroups";

export interface PickRow {
  doc: Doc;
  number: number | null;
  left: number; // lines not yet translated
}

export interface PickGroup {
  key: VolumeKey;
  label: string;
  rows: PickRow[];
}

/** The series' chapters for the Add dialog: by volume in reading order, the Illustrations chapter
 *  left out (it has no text), narrowed to titles containing `filter` (any case). Empty groups go. */
export function pickGroups(seriesId: number, docs: Doc[], volumes: Volume[], syosetu: boolean, filter: string): PickGroup[] {
  const needle = filter.trim().toLocaleLowerCase();
  return volumeGroups(seriesId, docs, volumes)
    .map((g) => ({
      key: g.key,
      label: g.volume?.label ?? "No volume",
      rows: g.docs
        .filter((d) => !d.is_illustrations)
        .map((d) => ({ doc: d, number: chapterNumber(g, d, syosetu), left: Math.max(0, d.line_count - d.translated_count) }))
        .filter((r) => !needle || r.doc.title.toLocaleLowerCase().includes(needle)),
    }))
    .filter((g) => g.rows.length > 0);
}

/** Tick every id in `ids`, or untick them all when every one is already ticked. */
export function toggleAll(picked: Set<number>, ids: number[]): Set<number> {
  const next = new Set(picked);
  if (ids.every((id) => next.has(id))) ids.forEach((id) => next.delete(id));
  else ids.forEach((id) => next.add(id));
  return next;
}
