export type SeriesFieldsValue = { title: string; originalTitle: string; originalAuthor: string; authorRomaji: string };

export const EMPTY_FIELDS: SeriesFieldsValue = { title: "", originalTitle: "", originalAuthor: "", authorRomaji: "" };

export function seriesBody(v: SeriesFieldsValue) {
  return {
    title: v.title.trim(),
    original_title: v.originalTitle.trim(),
    original_author: v.originalAuthor.trim(),
    author_romaji: v.authorRomaji.trim(),
  };
}

/** Form fields for `/epub/import` that create a new series with its credits. */
export function appendCredits(form: FormData, v: SeriesFieldsValue): void {
  const b = seriesBody(v);
  form.append("new_series", "true");
  form.append("series_title", b.title);
  form.append("original_title", b.original_title);
  form.append("original_author", b.original_author);
  form.append("author_romaji", b.author_romaji);
}

export function epubAuthorDefault(romaji: string, bookAuthor: string): string {
  return romaji.trim() || bookAuthor;
}
