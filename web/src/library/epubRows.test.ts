import { describe, expect, it } from "vitest";
import type { Schemas } from "../api/client";
import { bookRows } from "./epubRows";

const ch = (href: string, title: string, char_count: number, image_count: number) =>
  ({ href, title, order: 0, char_count, image_count, image_only: image_count > 0 && char_count === 0 }) as Schemas["BookChapter"];

describe("bookRows", () => {
  it("groups image-only chapters into one first row", () => {
    const rows = bookRows([ch("p1.xhtml", "plate", 0, 1), ch("p2.xhtml#b", "plate", 0, 1),
      ch("pro.xhtml", "Prologue", 900, 1), ch("c1.xhtml", "Chapter 1", 2000, 0)]);
    expect(rows).toEqual([
      { kind: "illustrations", hrefs: ["p1.xhtml", "p2.xhtml#b"], pages: 2, images: 2 },
      { kind: "chapter", href: "pro.xhtml", title: "Prologue", charCount: 900, imageCount: 1 },
      { kind: "chapter", href: "c1.xhtml", title: "Chapter 1", charCount: 2000, imageCount: 0 },
    ]);
  });

  it("no image-only, no row", () => {
    expect(bookRows([ch("c1.xhtml", "Chapter 1", 10, 0)]).map((r) => r.kind)).toEqual(["chapter"]);
  });
});
