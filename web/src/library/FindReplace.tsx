import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link } from "react-router";
import { api, call } from "../api/client";
import { invalidateLibrary } from "./queries";

type Params = { q: string; replace: string; caseSensitive: boolean };

/** Find across a series with a before/after preview; replace only the checked lines. A line
 *  is replaced only if it still equals the "before" the user reviewed. */
export default function FindReplace({ seriesId }: { seriesId: number }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<Params>({ q: "", replace: "", caseSensitive: false });
  const [searched, setSearched] = useState<Params | null>(null); // what the shown results were made with
  const [checked, setChecked] = useState<Set<number>>(new Set());
  const [notice, setNotice] = useState("");
  const search = useMutation({
    mutationFn: (p: Params) =>
      call(api.GET("/series/{series_id}/find", {
        params: { path: { series_id: seriesId }, query: { q: p.q, replace: p.replace, case_sensitive: p.caseSensitive } },
      })),
    onSuccess: (data) => setChecked(new Set(data.matches.flatMap((m, i) => (m.too_long ? [] : [i])))),
  });
  const replace = useMutation({
    mutationFn: (body: { find: string; replace: string; case_sensitive: boolean; targets: { document_id: number; line_number: number; before: string }[] }) =>
      call(api.POST("/series/{series_id}/replace", { params: { path: { series_id: seriesId } }, body })),
    onSuccess: async (r) => {
      setNotice(`Replaced ${r.replaced}${r.skipped ? `, skipped ${r.skipped} changed since the search` : ""}`);
      if (searched) search.mutate(searched);
      await invalidateLibrary(queryClient);
    },
  });
  const run = (e: FormEvent) => {
    e.preventDefault();
    if (!form.q) return;
    setNotice("");
    replace.reset();
    setSearched(form);
    search.mutate(form);
  };
  const matches = search.data?.matches ?? [];
  const k = checked.size;
  const apply = () => {
    if (!searched || !window.confirm(`Replace ${k} line(s) across the series?`)) return;
    setNotice("");
    replace.mutate({
      find: searched.q,
      replace: searched.replace,
      case_sensitive: searched.caseSensitive,
      targets: matches
        .filter((_, i) => checked.has(i))
        .map((m) => ({ document_id: m.document_id, line_number: m.line_number, before: m.before })),
    });
  };
  const toggle = (i: number) =>
    setChecked((c) => {
      const next = new Set(c);
      if (!next.delete(i)) next.add(i);
      return next;
    });
  const error = search.error ?? replace.error;
  return (
    <section>
      <h2>Find and replace</h2>
      <form className="toolbar" onSubmit={run}>
        <input aria-label="Find in series" value={form.q} maxLength={1000} required
          onChange={(e) => setForm({ ...form, q: e.target.value })} />
        <input aria-label="Replace with" value={form.replace}
          onChange={(e) => setForm({ ...form, replace: e.target.value })} />
        <label><input type="checkbox" checked={form.caseSensitive}
          onChange={(e) => setForm({ ...form, caseSensitive: e.target.checked })} /> Case sensitive</label>
        <button disabled={search.isPending}>Search</button>
      </form>
      {error && <p className="error" role="alert">{error.message}</p>}
      {notice && <p role="status">{notice}</p>}
      {search.data && (
        <>
          <p>{matches.length} matches{search.data.truncated ? " (showing the first 1000)" : ""}</p>
          {matches.length > 0 && (
            <>
              <table>
                <thead>
                  <tr>
                    <th><input type="checkbox" aria-label="Select all" checked={k > 0 && k === matches.filter((m) => !m.too_long).length}
                      onChange={(e) => setChecked(e.target.checked ? new Set(matches.flatMap((m, i) => (m.too_long ? [] : [i]))) : new Set())} /></th>
                    <th>Chapter</th><th>Line</th><th>Before</th><th>After</th>
                  </tr>
                </thead>
                <tbody>
                  {matches.map((m, i) => (
                    <tr key={`${m.document_id}:${m.line_number}`}>
                      <td><input type="checkbox" aria-label={`Select ${m.title} line ${m.line_number + 1}`}
                        checked={checked.has(i)} disabled={m.too_long} onChange={() => toggle(i)} /></td>
                      <td><Link to={`/documents/${m.document_id}`}>{m.title}</Link></td>
                      <td>{m.line_number + 1}</td>
                      <td>{m.before}</td>
                      <td>{m.too_long ? <span className="muted">Result too long to replace</span> : m.after}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <button onClick={apply} disabled={k === 0 || replace.isPending}>Replace selected ({k})</button>
            </>
          )}
        </>
      )}
    </section>
  );
}
