import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useId, useState, type FormEvent } from "react";
import { api, call } from "../api/client";

type Target = "/words" | { seriesId: number };

/** Add/remove list of spellcheck words, account-wide (`/words`) or for one series. */
export default function WordList({ path, title, hint }: { path: Target; title: string; hint: string }) {
  const queryClient = useQueryClient();
  const id = useId();
  const key = ["words", typeof path === "string" ? "account" : path.seriesId];
  const [word, setWord] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const words = useQuery({
    queryKey: key,
    queryFn: () => typeof path === "string"
      ? call(api.GET("/words"))
      : call(api.GET("/series/{series_id}/words", { params: { path: { series_id: path.seriesId } } })),
  });
  const refresh = () => queryClient.invalidateQueries({ queryKey: key });
  const add = useMutation({
    mutationFn: (w: string) => typeof path === "string"
      ? call(api.PUT("/words/{word}", { params: { path: { word: w } } }))
      : call(api.PUT("/series/{series_id}/words/{word}", { params: { path: { series_id: path.seriesId, word: w } } })),
    onSuccess: () => { setWord(""); refresh(); },
  });
  const remove = useMutation({
    mutationFn: (w: string) => typeof path === "string"
      ? call(api.DELETE("/words/{word}", { params: { path: { word: w } } }))
      : call(api.DELETE("/series/{series_id}/words/{word}", { params: { path: { series_id: path.seriesId, word: w } } })),
    onSuccess: refresh,
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const w = word.trim();
    setProblem(null);
    add.reset();
    if (!w) return;
    if (/\s/.test(w)) return setProblem("Select a single word first");
    if (w.includes("/")) return setProblem("Words with / can't be added");
    add.mutate(w);
  };
  const error = problem ?? words.error?.message ?? add.error?.message ?? remove.error?.message;
  return (
    <section className="panel sec" aria-labelledby={`${id}-h`}>
      <h2 id={`${id}-h`}>{title}</h2>
      <p className="hint">{hint}</p>
      <form className="toolbar" onSubmit={submit}>
        <label>Add word <input value={word} onChange={(e) => setWord(e.target.value)} /></label>
        <button type="submit" disabled={add.isPending}>Add</button>
      </form>
      {error && <p className="error" role="alert">{error}</p>}
      {words.data && (words.data.length === 0 ? <p className="muted">No words yet</p> : (
        <ul>
          {words.data.map((w) => (
            <li key={w}>
              <span>{w}</span>{" "}
              <button type="button" className="quiet" aria-label={`Remove “${w}”`} disabled={remove.isPending}
                onClick={() => remove.mutate(w)}>Remove</button>
            </li>
          ))}
        </ul>
      ))}
    </section>
  );
}
