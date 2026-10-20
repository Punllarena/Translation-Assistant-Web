import { byVolumeOrder, bySeriesOrder, firstCover, progressOf, type Doc, type Volume } from "./shelf";

export type VolumeKey = number | "none";

export interface VolumeGroup {
  key: VolumeKey;
  volume: Volume | null;
  docs: Doc[];
  coverImageId: number | null;
  progress: number;
}

function group(key: VolumeKey, volume: Volume | null, docs: Doc[]): VolumeGroup {
  return { key, volume, docs, coverImageId: firstCover(docs), progress: progressOf(docs) };
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

export function chapterNumber(g: VolumeGroup, doc: Doc, syosetu: boolean): number {
  return syosetu ? doc.series_order : g.docs.findIndex((d) => d.id === doc.id) + 1;
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
