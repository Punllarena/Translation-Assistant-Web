import { describe, expect, it } from "vitest";
import type { Doc, Volume } from "../shelf";
import { flatten, galleryGroups, imageActions, imageKey, type GalleryImage } from "./galleryGroups";

const volume = (id: number, series_id: number, volume_order: number) =>
  ({ id, series_id, volume_order, label: `Volume ${id}` }) as Volume;
const doc = (id: number, series_id: number, volume_id: number | null, o: Partial<Doc> = {}) =>
  ({ id, series_id, volume_id, series_order: id, chapter_number: id, title: `T${id}`,
    chapter_title: "", ...o }) as Doc;
const image = (id: number, o: Partial<GalleryImage> = {}) =>
  ({ id, kind: "image", volume_id: null, document_id: null, src_path: `${id}.png`,
    anchor_position: 0, exclude_export: false, ...o }) as GalleryImage;
const cover = (id: number, volume_id: number) =>
  image(id, { kind: "cover", volume_id, document_id: null, src_path: "cover.png" });

describe("galleryGroups", () => {
  const V = [volume(2, 1, 2), volume(1, 1, 1)];
  const D = [
    doc(1, 1, 1, { chapter_number: 1 }),
    doc(2, 1, 1, { chapter_number: 2 }),
    doc(3, 1, 2, { chapter_number: 1 }),
    doc(4, 1, null, { chapter_number: 3 }),
  ];
  const I = [
    cover(90, 1),
    image(10, { volume_id: 1, document_id: 1, anchor_position: 2 }),
    image(11, { volume_id: 1, document_id: 1, anchor_position: 0 }),
    image(12, { volume_id: 1, document_id: 2 }),
    image(13, { volume_id: 2, document_id: 3 }),
    image(14, { volume_id: null, document_id: 4 }),
  ];

  it("groups by volume with the cover first and loose chapters last", () => {
    const groups = galleryGroups(I, D, V);
    expect(groups.map((g) => g.key)).toEqual(["v1", "v2", "none"]);
    expect(groups[0].cover?.id).toBe(90);
    expect(groups[0].chapters.map((c) => c.doc.id)).toEqual([1, 2]);
    expect(groups[0].chapters[0].images.map((i) => i.id)).toEqual([11, 10]);
    expect(groups[2].label).toBe("No volume");
    expect(groups[2].chapters[0].doc.id).toBe(4);
  });

  it("keeps a volume with a cover but no images, drops an empty one", () => {
    const groups = galleryGroups([cover(90, 1)], [D[0]], V);
    expect(groups.map((g) => [g.key, g.cover?.id ?? null])).toEqual([["v1", 90]]);
  });

  it("filters to one volume", () => {
    expect(galleryGroups(I, D, V, 2).map((g) => g.key)).toEqual(["v2"]);
  });

  it("writes the heading with the chapter number, or the title alone", () => {
    const illus = doc(5, 1, 1, { chapter_number: null, is_illustrations: true,
      title: "Illustrations", chapter_title: "" });
    const groups = galleryGroups([image(15, { volume_id: 1, document_id: 5 }),
      image(14, { volume_id: 1, document_id: 1 })],
      [doc(1, 1, 1, { chapter_number: 3, chapter_title: "A Field" }), illus], V);
    expect(groups[0].chapters.map((c) => c.heading)).toEqual(["Ch. 3 · A Field", "Illustrations"]);
  });
});

describe("flatten", () => {
  it("follows display order: the cover, then each chapter's images", () => {
    const V = [volume(1, 1, 1)];
    const D = [doc(2, 1, 1, { chapter_number: 2 }), doc(1, 1, 1, { chapter_number: 1 })];
    const I = [
      image(20, { volume_id: 1, document_id: 2 }),
      cover(90, 1),
      image(10, { volume_id: 1, document_id: 1, anchor_position: 1 }),
      image(11, { volume_id: 1, document_id: 1, anchor_position: 0 }),
    ];
    expect(flatten(galleryGroups(I, D, V)).map((i) => i.id)).toEqual([90, 11, 10, 20]);
  });

  it("keys a cover and an image with the same id apart", () => {
    expect(imageKey(cover(7, 1))).not.toBe(imageKey(image(7)));
  });
});

describe("imageActions", () => {
  it("a loose chapter's image can only be deleted", () => {
    expect(imageActions(image(1, { document_id: 4 }), doc(4, 1, null), false))
      .toEqual({ cover: false, move: false, remove: true });
  });
  it("an image in a volume chapter can do everything", () => {
    expect(imageActions(image(1, { volume_id: 1, document_id: 1 }), doc(1, 1, 1), false))
      .toEqual({ cover: true, move: true, remove: true });
  });
  it("no move in a syosetu series or from the Illustrations chapter", () => {
    expect(imageActions(image(1, { volume_id: 1, document_id: 1 }), doc(1, 1, 1), true).move).toBe(false);
    expect(imageActions(image(1, { volume_id: 1, document_id: 1 }), doc(1, 1, 1, { is_illustrations: true }), false).move).toBe(false);
  });
  it("a cover tile is view only", () => {
    expect(imageActions(cover(9, 1), undefined, false)).toEqual({ cover: false, move: false, remove: false });
  });
});
