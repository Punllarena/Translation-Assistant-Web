import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { api, call } from "../api/client";

/** Frequent terms in a series that the series glossary lacks; add one with its translation. */
export default function PhraseSuggestions({ seriesId }: { seriesId: number }) {
  const queryClient = useQueryClient();
  const [terms, setTerms] = useState<{ term: string; count: number }[] | null>(null);
  const [translations, setTranslations] = useState<Record<string, string>>({});
  const [unavailable, setUnavailable] = useState("");
  const analyze = useMutation({
    mutationFn: (min_freq: number) =>
      call(api.POST("/series/{series_id}/phrase-suggestions", {
        params: { path: { series_id: seriesId } }, body: { min_freq },
      })),
    onSuccess: (r) => {
      setUnavailable(r.available ? "" : r.message ?? "Phrase suggestions are unavailable");
      setTerms(r.available ? r.terms : null);
      setTranslations({});
    },
  });
  const add = useMutation({
    mutationFn: ({ term }: { term: string }) =>
      call(api.POST("/series/{series_id}/glossary", {
        params: { path: { series_id: seriesId } }, body: { phrase: term, translation: translations[term].trim() },
      })),
    onSuccess: (_, { term }) => {
      queryClient.invalidateQueries({ queryKey: ["glossary", seriesId] });
      setTerms((t) => t && t.filter((x) => x.term !== term));
    },
  });
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    add.reset();
    analyze.mutate(Number(new FormData(e.currentTarget).get("min_freq")) || 2);
  };
  const error = analyze.error ?? add.error;
  return (
    <section>
      <h2>Phrase suggestions</h2>
      <form className="toolbar" onSubmit={submit}>
        <label>Min frequency <input name="min_freq" type="number" min={1} max={999} defaultValue={2} /></label>
        <button disabled={analyze.isPending}>Analyze</button>
      </form>
      {unavailable && <p className="error" role="alert">{unavailable}</p>}
      {error && <p className="error" role="alert">{error.message}</p>}
      {terms && (terms.length === 0 ? <p className="muted">No new candidates</p> : (
        <table>
          <thead><tr><th>Term</th><th>Count</th><th>Translation</th><th /></tr></thead>
          <tbody>
            {terms.map((t) => (
              <tr key={t.term}>
                <td>{t.term}</td>
                <td>{t.count}</td>
                <td><input aria-label={`Translation for ${t.term}`} value={translations[t.term] ?? ""}
                  onChange={(e) => setTranslations({ ...translations, [t.term]: e.target.value })} /></td>
                <td><button disabled={!(translations[t.term] ?? "").trim() || add.isPending}
                  onClick={() => add.mutate({ term: t.term })}>Add</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      ))}
    </section>
  );
}
