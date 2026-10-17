import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, call, type Schemas } from "../api/client";
import JobProgress from "../jobs/JobProgress";
import { postForm } from "../library/upload";

type Kind = "edict" | "conjugations";
const LABEL: Record<Kind, string> = { edict: "EDICT2", conjugations: "Conjugations" };

export default function DictionaryPanel() {
  const queryClient = useQueryClient();
  const [jobId, setJobId] = useState<number | null>(null);
  const [failure, setFailure] = useState("");
  const q = useQuery({ queryKey: ["admin", "dictionary"], queryFn: () => call(api.GET("/admin/dictionary")) });
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["admin", "dictionary"] });
  const download = useMutation({
    mutationFn: () => call(api.POST("/admin/dictionary/edict/download")),
    onSuccess: (job) => { setFailure(""); setJobId(job.id); },
  });
  const upload = useMutation({
    mutationFn: ({ kind, file }: { kind: Kind; file: File }) => {
      const form = new FormData();
      form.append("file", file);
      return postForm<Schemas["DictFileOut"]>(`/admin/dictionary/${kind}`, form);
    },
    onSuccess: refresh,
  });
  const remove = useMutation({
    mutationFn: (kind: Kind) => call(api.DELETE("/admin/dictionary/{kind}", { params: { path: { kind } } })),
    onSuccess: refresh,
  });
  const error = q.error ?? download.error ?? upload.error ?? remove.error;
  return (
    <section className="panel sec" aria-labelledby="dict-h">
      <div className="sec-head"><h2 id="dict-h">Dictionary</h2></div>
      <p className="hint">JParser and MeCab glosses use EDICT2 by the Electronic Dictionary Research and Development Group (EDRDG), licensed CC BY-SA 4.0.</p>
      {error && <p className="error" role="alert">{error.message.replace(/^File too large$/, "File too large (64 MB max)")}</p>}
      {failure && <p className="error" role="alert">{failure}</p>}
      {q.data && (["edict", "conjugations"] as const).map((kind) => {
        const s = q.data[kind];
        const fromEnv = s.source === "env";
        return (
          <div key={kind} className="field" role="group" aria-label={LABEL[kind]}>
            <strong>{LABEL[kind]}</strong>{" "}
            <span className="muted" role="status">
              {s.present ? `Installed · ${s.entries ?? 0} ${kind === "edict" ? "entries" : "rules"}` : "Not installed"}
              {fromEnv && " · set by the server's environment"}
            </span>
            {!fromEnv && (
              <div className="toolbar">
                {kind === "edict" && <button type="button" className="primary" disabled={download.isPending || jobId !== null} onClick={() => download.mutate()}>Download from EDRDG</button>}
                <input type="file" aria-label={`Upload ${LABEL[kind]}`}
                  onChange={(e) => { const file = e.currentTarget.files?.[0]; if (file) upload.mutate({ kind, file }); e.currentTarget.value = ""; }} />
                {s.present && <button type="button" onClick={() => remove.mutate(kind)}>Remove</button>}
              </div>
            )}
          </div>
        );
      })}
      {jobId !== null && <JobProgress jobId={jobId} outcome={() => null} onDone={(j) => { if (j.state !== "done") setFailure(j.state === "cancelled" ? "Cancelled" : j.message || "The download failed"); setJobId(null); void refresh(); }} />}
    </section>
  );
}
