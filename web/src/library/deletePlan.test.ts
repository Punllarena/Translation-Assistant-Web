import { describe, expect, it } from "vitest";
import type { Doc } from "./shelf";
import { deletePlan } from "./deletePlan";

const doc = (over: Partial<Doc> = {}) =>
  ({ id: 1, image_count: 0, volume_id: null, is_illustrations: false, ...over }) as Doc;

describe("deletePlan", () => {
  it("mixed selection", () => {
    const docs = [doc({ image_count: 2, volume_id: 1 }), doc({ image_count: 1, volume_id: null }), doc({ image_count: 0 })];
    expect(deletePlan(docs, false)).toEqual({ withImages: 2, movable: 1, stuck: 1, images: 3 });
  });

  it("syosetu series never moves", () => {
    expect(deletePlan([doc({ image_count: 1, volume_id: 1 })], true).movable).toBe(0);
  });

  it("an Illustrations chapter's images are already where they would go", () => {
    const plan = deletePlan([doc({ image_count: 3, volume_id: 1, is_illustrations: true })], false);
    expect(plan).toEqual({ withImages: 1, movable: 0, stuck: 1, images: 3 });
  });
});
