import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router";
import type { Schemas } from "../../api/client";
import { EpubFields, EpubPicker, EpubResult, epubError, useEpubBook } from "../epubBook";
import { invalidateLibrary } from "../queries";
import { postForm } from "../upload";
import { EMPTY_FIELDS, appendCredits, epubAuthorDefault, type SeriesFieldsValue } from "./fields";
import SeriesFields from "./SeriesFields";

export default function NewFromEpub() {
  const queryClient = useQueryClient();
  const [value, setValue] = useState<SeriesFieldsValue>(EMPTY_FIELDS);
  const lastAuthor = useRef(""); // the volume Author we last set: a different value means the user edited it
  const epub = useEpubBook({
    onPick: () => run.reset(),
    onBook: (b) => {
      lastAuthor.current = b.author;
      setValue((v) => ({ ...v, originalTitle: v.originalTitle || b.title, originalAuthor: v.originalAuthor || b.author }));
    },
  });
  const { book, meta, setMeta } = epub;
  useEffect(() => {
    if (!book || meta.author !== lastAuthor.current) return;
    const next = epubAuthorDefault(value.authorRomaji, book.author);
    lastAuthor.current = next;
    if (next !== meta.author) setMeta({ ...meta, author: next });
  }, [book, meta, setMeta, value.authorRomaji]);
  const run = useMutation({
    mutationFn: () => {
      const form = epub.importForm({ id: "", title: "" });
      appendCredits(form, value);
      return postForm<Schemas["EpubImportOut"]>("/epub/import", form);
    },
    onSuccess: () => invalidateLibrary(queryClient),
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!run.isPending) run.mutate();
  };
  const error = epubError(epub.inspect.error ?? run.error);
  const r = run.data;
  return (
    <form className="panel pad" onSubmit={submit}>
      <h2 className="sec">EPUB</h2>
      <p className="muted">Start from an EPUB of a volume you have.</p>
      <EpubPicker epub={epub} disabled={run.isPending} />
      {book && (
        <>
          <SeriesFields value={value} onChange={setValue} disabled={run.isPending} />
          <EpubFields epub={epub} />
          <div className="row-fields">
            <button type="submit" className="primary"
              disabled={value.title.trim() === "" || !epub.checked.size || run.isPending}>Import</button>
          </div>
        </>
      )}
      {error && <p className="error" role="alert">{error}</p>}
      {r && <EpubResult r={r}><p><Link to={`/series/${r.series_id}`}>Open series</Link></p></EpubResult>}
    </form>
  );
}
