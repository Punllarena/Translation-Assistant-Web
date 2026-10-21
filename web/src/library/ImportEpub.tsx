import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState, type FormEvent } from "react";
import { Link } from "react-router";
import type { Schemas } from "../api/client";
import type { SeriesRow } from "./shelf";
import { invalidateLibrary, useAllVolumes } from "./queries";
import SeriesChoice, { seriesChosen, type Choice } from "./SeriesChoice";
import { EpubFields, EpubPicker, EpubResult, epubError, useEpubBook } from "./epubBook";
import { postForm } from "./upload";

const NONE: Schemas["VolumeOut"][] = [];

/** Two steps, as the desktop ImportEpubDialog: inspect the book, then import the checked chapters. */
export default function ImportEpub({ series }: { series: SeriesRow[] }) {
  const queryClient = useQueryClient();
  const [choice, setChoice] = useState<Choice>({ id: "", title: "" });
  const allVolumes = useAllVolumes().data;
  // The name pre-fill follows the chosen series: an existing one's title and volumes, or the typed title.
  const chosen = choice.id ? series.find((s) => String(s.id) === choice.id) : undefined;
  const seriesTitle = chosen ? chosen.title : choice.title;
  const volumes = useMemo(
    () => (chosen && allVolumes ? allVolumes.filter((v) => v.series_id === chosen.id) : NONE),
    [chosen, allVolumes],
  );
  const epub = useEpubBook({
    onPick: () => run.reset(), onBook: (b) => setChoice({ id: "", title: b.title }), seriesTitle, volumes,
  });
  const run = useMutation({
    mutationFn: () => postForm<Schemas["EpubImportOut"]>("/epub/import", epub.importForm(choice)),
    onSuccess: () => invalidateLibrary(queryClient),
  });
  const { book, file } = epub;
  const submit = (e: FormEvent) => {
    e.preventDefault();
    run.mutate();
  };
  const r = run.data;
  const error = epubError(epub.inspect.error ?? run.error);
  return (
    <form className="panel sec" aria-labelledby="import-epub-h" onSubmit={submit}>
      <div className="sec-head">
        <h2 id="import-epub-h">EPUB</h2>
        {file && <span className="muted mono">{file.name}</span>}
      </div>
      <EpubPicker epub={epub} />
      {book && (
        <>
          <SeriesChoice series={series} value={choice} onChange={setChoice} />
          <EpubFields epub={epub} />
          <div className="inline-form">
            <button className="primary" disabled={!seriesChosen(choice) || !epub.checked.size || run.isPending}>Import</button>
            <span className="muted">{epub.checked.size} chapters selected · {book.chapters.length - epub.checked.size} unchecked</span>
          </div>
        </>
      )}
      {error && <p className="error" role="alert">{error}</p>}
      {r && <EpubResult r={r}><p><Link to={`/series/${r.series_id}`}>Open series</Link></p></EpubResult>}
    </form>
  );
}
