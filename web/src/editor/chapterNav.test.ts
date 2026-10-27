import { describe, expect, it } from "vitest";
import { chapterNeighbours } from "./chapterNav";
import type { Doc } from "../library/shelf";

const doc = (id: number, o: Partial<Doc> = {}): Doc =>
  ({ id, series_id: 1, volume_id: 10, series_order: id, chapter_number: id, progress: 0, title: `T${id}`, ...o }) as unknown as Doc;

describe("chapterNeighbours", () => {
  const docs = [doc(3), doc(1), doc(2)];
  it("middle has both neighbours", () => {
    const r = chapterNeighbours(docs, 2);
    expect(r.prev?.id).toBe(1);
    expect(r.next?.id).toBe(3);
    expect(r.volume.map((d) => d.id)).toEqual([1, 2, 3]);
  });
  it("first has no prev", () => {
    const r = chapterNeighbours(docs, 1);
    expect(r.prev).toBeNull();
    expect(r.next?.id).toBe(2);
  });
  it("last has no next", () => {
    const r = chapterNeighbours(docs, 3);
    expect(r.next).toBeNull();
    expect(r.prev?.id).toBe(2);
  });
  it("an illustrations chapter sits by series_order", () => {
    const d = [doc(1, { series_order: 2 }), doc(2, { series_order: 1, chapter_number: null })];
    expect(chapterNeighbours(d, 2).next?.id).toBe(1);
  });
  it("a loose chapter's volume lists only loose chapters", () => {
    const d = [doc(1, { volume_id: null }), doc(2), doc(3, { volume_id: null })];
    expect(chapterNeighbours(d, 1).volume.map((x) => x.id)).toEqual([1, 3]);
    expect(chapterNeighbours(d, 1).next?.id).toBe(2);
  });
  it("a one-chapter series has no neighbours", () => {
    const r = chapterNeighbours([doc(1)], 1);
    expect(r.prev).toBeNull();
    expect(r.next).toBeNull();
  });
  it("ignores other series", () => {
    const r = chapterNeighbours([doc(1), doc(2, { series_id: 2 })], 1);
    expect(r.next).toBeNull();
    expect(r.volume.map((d) => d.id)).toEqual([1]);
  });
  it("unknown id", () => {
    expect(chapterNeighbours(docs, 99)).toEqual({ prev: null, next: null, volume: [] });
  });
});
