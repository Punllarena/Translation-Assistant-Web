import { byVolumeOrder, bySeriesOrder, progressOf, type Doc, type Volume } from "./shelf";

export type VolumeKey = number | "none";

export interface VolumeGroup {
  key: VolumeKey;
  volume: Volume | null;
  docs: Doc[];
  coverImageId: number | null;
  progress: number;
}

function group(key: VolumeKey, volume: Volume | null, docs: Doc[]): VolumeGroup {
  return { key, volume, docs, coverImageId: volume?.cover_id ?? null, progress: progressOf(docs) };
}

export function volumeGroups(seriesId: number, docs: Doc[], volumes: Volume[]): VolumeGroup[] {
  const own = docs.filter((d) => d.series_id === seriesId).sort(bySeriesOrder);
  const vols = volumes.filter((v) => v.series_id === seriesId).sort(byVolumeOrder);
  const known = new Set(vols.map((v) => v.id));
  const groups = vols.map((v) => group(v.id, v, own.filter((d) => d.volume_id === v.id)));
  const loose = own.filter((d) => d.volume_id == null || !known.has(d.volume_id));
  if (loose.length > 0 || groups.length === 0) groups.push(group("none", null, loose));
  return groups;
}

/** The number shown for `doc`: none for the Illustrations chapter, which stands outside the numbering. */
export function chapterNumber(g: VolumeGroup, doc: Doc, syosetu: boolean): number | null {
  if (doc.is_illustrations) return null;
  return syosetu ? doc.series_order : g.docs.filter((d) => !d.is_illustrations).findIndex((d) => d.id === doc.id) + 1;
}

export function pickVolume(param: string | null, groups: VolumeGroup[]): VolumeKey | null {
  const hit = groups.find((g) => String(g.key) === param);
  return hit ? hit.key : (groups[0]?.key ?? null);
}

/** Every chapter id of the series in reading order, with group `key`'s chapters replaced by `docs`
 *  (the body of `PUT /series/{id}/order` after a drag within one volume). */
export function seriesOrder(groups: VolumeGroup[], key: VolumeKey, docs: Doc[]): number[] {
  return groups.flatMap((g) => (g.key === key ? docs : g.docs)).map((d) => d.id);
}

export const BLOCK_SIZE = 100;

export interface ChapterBlock {
  start: number; // index of the block's first chapter in the group's list
  docs: Doc[];
  label: string; // "101–200": the chapter numbers shown, first to last
  progress: number;
}

/** A long chapter list cut into view-only blocks of `size`, so only the open ones render; none
 *  when the list fits in one. Nothing about the chapters changes. */
export function chapterBlocks(g: VolumeGroup, syosetu: boolean, size = BLOCK_SIZE): ChapterBlock[] {
  if (g.docs.length <= size) return [];
  const blocks: ChapterBlock[] = [];
  for (let start = 0; start < g.docs.length; start += size) {
    const docs = g.docs.slice(start, start + size);
    const nums = docs.map((d) => chapterNumber(g, d, syosetu)).filter((n): n is number => n !== null);
    const label = nums.length === 0 ? "Illustrations"
      : nums[0] === nums[nums.length - 1] ? String(nums[0]) : `${nums[0]}–${nums[nums.length - 1]}`;
    blocks.push({ start, docs, label, progress: progressOf(docs) });
  }
  return blocks;
}

/** The block to open first: the first one not fully translated, else the first. */
export function firstOpenBlock(blocks: ChapterBlock[]): number {
  return Math.max(0, blocks.findIndex((b) => b.progress < 100));
}
