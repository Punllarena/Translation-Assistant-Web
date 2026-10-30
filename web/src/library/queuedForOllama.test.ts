import { describe, expect, it } from "vitest";
import type { Doc } from "./shelf";
import { queuedIds } from "./queuedForOllama";

const doc = (id: number, series_id: number, volume_id: number | null) =>
  ({ id, series_id, volume_id }) as Doc;

describe("queuedIds", () => {
  const docs = [doc(1, 10, 100), doc(2, 10, 100), doc(3, 10, 200), doc(4, 20, 300)];

  it("takes only a documents item's own ids", () => {
    const items = [{ kind: "documents", series_id: 10, volume_id: null, document_ids: [2, 4] }];
    expect([...queuedIds(items, docs)].sort()).toEqual([2, 4]);
  });

  it("takes every shown chapter of a queued volume or series", () => {
    const volume = [{ kind: "volume", series_id: 10, volume_id: 100, document_ids: [] }];
    expect([...queuedIds(volume, docs)].sort()).toEqual([1, 2]);
    const series = [{ kind: "series", series_id: 10, volume_id: null, document_ids: [] }];
    expect([...queuedIds(series, docs)].sort()).toEqual([1, 2, 3]);
  });

  it("is empty without items", () => {
    expect(queuedIds([], docs).size).toBe(0);
  });
});
