import type { Doc } from "./shelf";

export interface QueueItemLike {
  kind: string;
  series_id: number;
  volume_id: number | null;
  document_ids: number[];
}

/** The chapter ids queued Ollama work covers among `docs` (the rows on screen): a documents
 *  item names its own ids; a volume or series item covers every shown chapter of that scope. */
export function queuedIds(items: QueueItemLike[], docs: Doc[]): Set<number> {
  const ids = new Set<number>();
  for (const item of items) {
    const covered =
      item.kind === "documents" ? item.document_ids
      : item.kind === "volume" ? docs.filter((d) => d.volume_id === item.volume_id).map((d) => d.id)
      : docs.filter((d) => d.series_id === item.series_id).map((d) => d.id);
    for (const id of covered) ids.add(id);
  }
  return ids;
}
