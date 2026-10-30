import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api, ApiError, call, type Schemas } from "../api/client";
import type { Doc } from "../library/shelf";
import { invalidateLibrary } from "../library/queries";
import { ConfirmDialog } from "../ui/Dialog";
import { browserZone, defaultSlot, fromLocalInput, toLocalInput } from "../time";
import { confirmLabel, statusTone } from "./label";

const LABEL: Record<string, string> = { publish: "Published", future: "Scheduled", draft: "Draft", "": "Not published" };

/** How the publish dialog was reached: the tag's Reschedule / Update post, or a plain Publish. */
export type PublishMode = "publish" | "reschedule" | "update";

const HEADING: Record<PublishMode, string> = {
  publish: "Publish to WordPress", reschedule: "Reschedule", update: "Update post",
};

/** Publish one chapter: live status, the previous-chapter warning, optional schedule, then the result.
 *  `reschedule` opens with the schedule on and prefilled from the stored time, and confirms the
 *  republish itself — the user already chose to reschedule. */
export default function PublishDialog({ doc, onClose, mode = "publish" }: {
  doc: Doc; onClose: () => void; mode?: PublishMode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => { const d = ref.current; if (d && !d.open) d.showModal(); }, []);
  const queryClient = useQueryClient();
  const id = { params: { path: { document_id: doc.id } } };
  const status = useQuery({
    queryKey: ["wp", "status", doc.id], retry: false, gcTime: 0, refetchOnWindowFocus: false,
    queryFn: () => call(api.POST("/documents/{document_id}/wp/status", { ...id, params: { ...id.params, query: { tz: browserZone() } } })),
  });
  const prefs = useQuery({ queryKey: ["wp", "prefs"], queryFn: () => call(api.GET("/wp/prefs")) });
  const [schedule, setSchedule] = useState<boolean | null>(mode === "reschedule" ? true : null);
  const [when, setWhen] = useState(doc.wp_scheduled_for ? toLocalInput(new Date(doc.wp_scheduled_for)) : "");
  const [result, setResult] = useState<Schemas["PublishOut"] | null>(null);
  const [conflict, setConflict] = useState<string | null>(null);
  const suggested = status.data?.suggested_slot ? new Date(status.data.suggested_slot) : null;
  const scheduling = schedule ?? !!status.data?.previous_scheduled;
  const slot = when || toLocalInput(suggested ?? defaultSlot(prefs.data?.wp_default_schedule_time ?? ""));
  const run = useMutation({
    mutationFn: (confirm: boolean) =>
      call(api.POST("/documents/{document_id}/wp/publish", { ...id, body: {
        scheduled_for: scheduling ? fromLocalInput(slot) : null,
        confirm_republish: mode === "reschedule" || confirm,
      } })),
    onSuccess: (r) => { setResult(r); return invalidateLibrary(queryClient); },
    onError: (e) => {
      if (e instanceof ApiError && e.status === 409) setConflict(e.message);
    },
  });
  const chapter = doc.chapter_number === 0 ? "Synopsis" : `Chapter ${doc.chapter_number}`;
  const statusText = status.isPending ? "checking…" : status.data ? (LABEL[status.data.status] ?? status.data.status) : "unknown";
  const title = doc.chapter_title || doc.title;
  return (
    <dialog ref={ref} onClose={onClose} onCancel={(e) => { if (run.isPending) e.preventDefault(); }}
      aria-label={HEADING[mode]} className="dlg">
      <div className="dlg-head">
        <span className="label">{HEADING[mode]}</span>
        <h2>{title}</h2>
        <p className="muted">{chapter}</p>
      </div>
      {result ? (
        <div className="dlg-body">
          <p className="box ok" role="status">{result.created || result.updated ? (result.scheduled_for ? "Scheduled!" : result.created ? "Published!" : "Updated!") : "Already published."}</p>
          {result.page_url && <p>Page: <a href={result.page_url} target="_blank" rel="noreferrer">{result.page_url}</a></p>}
          {result.post_url && <p>Post: <a href={result.post_url} target="_blank" rel="noreferrer">{result.post_url}</a></p>}
          {result.password && (
            <label className="field"><span>Password (copy this)</span>
              <input readOnly className="mono" value={result.password} onFocus={(e) => e.currentTarget.select()} /></label>
          )}
          {result.unlock_chapter_index !== null && <p className="muted">Chapter {result.unlock_chapter_index} is now unlocked.</p>}
        </div>
      ) : (
        <div className="dlg-body">
          <p>WP status: <span className={`badge ${statusTone(status.data?.status ?? "")}`}>{statusText}</span>
            {status.data?.remote_error && <span className="muted"> (cached — {status.data.remote_error})</span>}</p>
          {status.data?.status === "publish" && <p className="muted">Republishing will overwrite the live chapter.</p>}
          {status.data?.previous_scheduled && (
            <p className="box warn">Chapter {(doc.chapter_number ?? 0) - 1} is still scheduled and hasn't gone live yet.</p>
          )}
          <label className="check"><input type="checkbox" checked={scheduling} onChange={(e) => setSchedule(e.target.checked)} /><span>Schedule for later</span></label>
          <label className="field"><span>When</span>
            <input type="datetime-local" className="mono" disabled={!scheduling} value={slot} onChange={(e) => setWhen(e.target.value)} /></label>
        </div>
      )}
      {(status.error ?? run.error) && <p className="error" role="alert">{(status.error ?? run.error)!.message}</p>}
      {conflict !== null && !result && (
        <ConfirmDialog title="Publish anyway?" confirmLabel="Publish anyway" busy={run.isPending}
          message={conflict} error={run.error?.message} onConfirm={() => { setConflict(null); run.mutate(true); }}
          onClose={() => setConflict(null)} />
      )}
      <div className="dlg-foot">
        <button type="button" onClick={onClose}>{result ? "Close" : "Cancel"}</button>
        {!result && (
          <button type="button" className="primary" disabled={run.isPending || status.isPending || status.isError} onClick={() => run.mutate(false)}>
            {confirmLabel(!!status.data?.previous_scheduled, scheduling)}
          </button>
        )}
      </div>
    </dialog>
  );
}
