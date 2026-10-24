import type { Schemas } from "../api/client";

export type BookRow =
  | { kind: "chapter"; href: string; title: string; charCount: number; imageCount: number }
  | { kind: "illustrations"; hrefs: string[]; pages: number; images: number };

/** The picker's rows: the book's image-only pages folded into one Illustrations row, placed first
 *  (the import gathers them into the volume's Illustrations chapter), then the other chapters. */
export function bookRows(chapters: Schemas["BookChapter"][]): BookRow[] {
  const plates = chapters.filter((c) => c.image_only);
  const rows: BookRow[] = chapters.filter((c) => !c.image_only).map((c) => ({
    kind: "chapter", href: c.href, title: c.title, charCount: c.char_count, imageCount: c.image_count,
  }));
  if (plates.length === 0) return rows;
  const images = plates.reduce((n, c) => n + c.image_count, 0);
  return [{ kind: "illustrations", hrefs: plates.map((c) => c.href), pages: plates.length, images }, ...rows];
}
