import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, ApiError, call } from "../api/client";
import JobProgress from "../jobs/JobProgress";
import type { Doc } from "../library/shelf";
import { invalidateLibrary } from "../library/queries";
import { ConfirmDialog, Modal } from "../ui/Dialog";
import { confirmLabel } from "./label";

const LIVE = ["publish", "future"];

/** Publish the volume's Illustrations chapter as its illustrations page: the confirm, the overwrite
 *  question when the page is already live, then the job's progress. A job still running from before
 *  a reload is picked up instead. */
export default function IllustrationsPublish({ doc, onClose }: { doc: Doc; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [newJob, setNewJob] = useState<number | null>(null);
  const [conflict, setConflict] = useState<string | null>(null); // the 409, asking to overwrite
  const active = useQuery({
    queryKey: ["jobs", "active", "wp_illustrations", doc.id], gcTime: 0,
    queryFn: () => call(api.GET("/jobs", { params: { query: { active: true } } })),
  });
  const jobId = newJob ?? active.data?.find(
    (j) => j.kind === "wp_illustrations" && (j.params as { document_id?: number } | null)?.document_id === doc.id)?.id ?? null;
  const start = useMutation({
    mutationFn: async (confirm_republish: boolean) => {
      const post = () => call(api.POST("/documents/{document_id}/wp/illustrations", {
        params: { path: { document_id: doc.id } }, body: { confirm_republish },
      }));
      try {
        return await post();
      } catch (e) {
        if (confirm_republish || !(e instanceof ApiError) || e.status !== 409 || !LIVE.includes(doc.wp_status)) throw e;
        setConflict(e.message);
        return null;
      }
    },
    onSuccess: (job) => { if (job) { setConflict(null); setNewJob(job.id); } },
  });
  const close = () => { void invalidateLibrary(queryClient); onClose(); };
  if (conflict !== null && jobId === null) {
    return (
      <ConfirmDialog title="Overwrite the Illustrations page?" confirmLabel="Publish anyway" danger busy={start.isPending}
        message={conflict} error={start.error?.message} onConfirm={() => start.mutate(true)} onClose={close} />
    );
  }
  return (
    <Modal title="Publish Illustrations" onClose={close} busy={start.isPending}>
      <div className="dlg-head">
        <span className="label">Publish to WordPress</span>
        <h2>Illustrations</h2>
      </div>
      <div className="dlg-body">
        {jobId !== null ? (
          <JobProgress jobId={jobId} onDone={() => invalidateLibrary(queryClient)} outcome={(j) => {
            const r = (j.result ?? {}) as { page_url?: string; created?: boolean };
            return <p>{j.state === "cancelled" ? "Cancelled" : `${r.created ? "Created" : "Updated"} the Illustrations page`}{" "}
              {r.page_url && <a href={r.page_url} target="_blank" rel="noreferrer">{r.page_url}</a>}</p>;
          }} />
        ) : (
          <p>Publish the Illustrations page of this volume to WordPress? It shows every illustration in the volume, published or not.</p>
        )}
        {(active.error ?? start.error) && <p className="error" role="alert">{(active.error ?? start.error)!.message}</p>}
      </div>
      <div className="dlg-foot">
        <button type="button" disabled={start.isPending} onClick={close}>{jobId !== null ? "Close" : "Cancel"}</button>
        {jobId === null && (
          <button type="button" className="primary" disabled={start.isPending || active.isPending}
            onClick={() => start.mutate(false)}>{confirmLabel(false, false)}</button>
        )}
      </div>
    </Modal>
  );
}
