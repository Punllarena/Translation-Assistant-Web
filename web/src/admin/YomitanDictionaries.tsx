import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, call, type Schemas } from "../api/client";
import JobProgress from "../jobs/JobProgress";
import { postForm } from "../library/upload";
import { ConfirmDialog } from "../ui/Dialog";

const KIND = "yomitan_import";

export default function YomitanDictionaries() {
  const queryClient = useQueryClient();
  const [jobId, setJobId] = useState<number | null>(null);
  const [failure, setFailure] = useState("");
  const [done, setDone] = useState("");
  const [removing, setRemoving] = useState<Schemas["YomitanDictOut"] | null>(null);
  // An import started earlier (or in another tab) is picked up again on return.
  const active = useQuery({
    queryKey: ["jobs", "active", KIND], gcTime: 0,
    queryFn: () => call(api.GET("/jobs", { params: { query: { active: true } } })),
  });
  const running = jobId ?? active.data?.find((j) => j.kind === KIND)?.id ?? null;
  const q = useQuery({ queryKey: ["admin", "dictionary"], queryFn: () => call(api.GET("/admin/dictionary")) });
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["admin", "dictionary"] });
  const upload = useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append("file", file);
      return postForm<Schemas["JobOut"]>("/admin/dictionary/yomitan", form);
    },
    onSuccess: (job) => { setFailure(""); setDone(""); setJobId(job.id); },
  });
  const reorder = useMutation({
    mutationFn: (order: string[]) => call(api.PUT("/admin/dictionary/order", { body: { order } })),
    onSuccess: refresh,
  });
  const remove = useMutation({
    mutationFn: (id: number) => call(api.DELETE("/admin/dictionary/yomitan/{dictionary_id}", { params: { path: { dictionary_id: id } } })),
    onSuccess: () => { setRemoving(null); void refresh(); },
  });
  const byToken = new Map((q.data?.yomitan ?? []).map((d) => [`yomitan:${d.id}`, d]));
  const order = q.data?.order ?? [];
  const nameOf = (token: string) => (token === "edict" ? "EDICT2" : byToken.get(token)?.title ?? token);
  const move = (i: number, by: number) => {
    const next = [...order];
    [next[i], next[i + by]] = [next[i + by], next[i]];
    reorder.mutate(next);
  };
  const error = q.error ?? upload.error ?? reorder.error;
  return (
    <section className="field" aria-labelledby="yomitan-h">
      <h3 id="yomitan-h">Yomitan dictionaries</h3>
      <p className="hint">JParser shows a one-line meaning. For full entries, install the Yomitan browser extension and import the same dictionaries there. <a href="https://yomitan.wiki" target="_blank" rel="noreferrer">yomitan.wiki</a></p>
      {error && <p className="error" role="alert">{error.message}</p>}
      {failure && <p className="error" role="alert">{failure}</p>}
      {done && <p className="muted" role="status">{done}</p>}
      <div className="toolbar">
        <input type="file" accept=".zip" aria-label="Upload Yomitan dictionary" disabled={upload.isPending || running !== null}
          onChange={(e) => { const file = e.currentTarget.files?.[0]; if (file) upload.mutate(file); e.currentTarget.value = ""; }} />
      </div>
      {running !== null && (
        <JobProgress jobId={running} outcome={() => null} onDone={(j) => {
          if (j.state === "done") setDone(String((j.result as { message?: string } | null)?.message ?? "Installed"));
          else setFailure(j.state === "cancelled" ? "Cancelled" : j.message || "The import failed");
          setJobId(null);
          queryClient.removeQueries({ queryKey: ["jobs", "active", KIND] });
          void active.refetch();
          void refresh();
        }} />
      )}
      <ol aria-label="Dictionary order">
        {order.map((token, i) => {
          const d = byToken.get(token);
          const name = nameOf(token);
          return (
            <li key={token}>
              <strong>{name}</strong>
              {token === "edict" && q.data && !q.data.edict.present && <span className="muted"> · not installed</span>}
              {d && <span className="muted"> · {d.revision} · {d.entries} entries{d.attribution ? ` · ${d.attribution}` : ""}</span>}
              {" "}
              <button type="button" aria-label={`Move ${name} up`} disabled={i === 0 || reorder.isPending} onClick={() => move(i, -1)}>↑</button>
              <button type="button" aria-label={`Move ${name} down`} disabled={i === order.length - 1 || reorder.isPending} onClick={() => move(i, 1)}>↓</button>
              {d && <button type="button" aria-label={`Remove ${d.title}`} onClick={() => setRemoving(d)}>Remove</button>}
            </li>
          );
        })}
      </ol>
      {removing && (
        <ConfirmDialog title="Remove dictionary" confirmLabel="Remove" danger busy={remove.isPending}
          message={<>Remove {removing.title} and its {removing.entries} entries?</>}
          error={remove.error?.message ?? null}
          onConfirm={() => remove.mutate(removing.id)} onClose={() => { remove.reset(); setRemoving(null); }} />
      )}
    </section>
  );
}
