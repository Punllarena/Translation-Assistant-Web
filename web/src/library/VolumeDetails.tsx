import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { api, call, type Schemas } from "../api/client";
import JobProgress from "../jobs/JobProgress";
import { ConfirmDialog, Modal } from "../ui/Dialog";
import type { SeriesRow, Volume } from "./shelf";
import VolumeNameFields, { type VolumeName } from "./VolumeNameFields";
import { render } from "./volumeNames";
import { invalidateLibrary } from "./queries";

const EPUB_FIELDS = [
  ["epub_title", "EPUB title"], ["epub_author", "Author"], ["epub_language", "Language"],
  ["epub_illustrator", "Illustrator"], ["epub_publisher", "Publisher"],
  ["epub_identifier", "Identifier"], ["epub_description", "Description"],
] as const;

/** The volume's title and EPUB metadata, in a dialog. */
export default function VolumeDetails({ volume, series, kinds, onClose }: {
  volume: Volume; series: SeriesRow; kinds: string[]; onClose: () => void;
}) {
  const [name, setName] = useState<VolumeName>({
    kind: volume.kind, index: volume.volume_index ?? "", subtitle: volume.subtitle,
  });
  const queryClient = useQueryClient();
  const save = useMutation({
    mutationFn: (body: Schemas["VolumeUpdate"]) =>
      call(api.PATCH("/volumes/{volume_id}", { params: { path: { volume_id: volume.id } }, body })),
    onSuccess: async () => {
      await invalidateLibrary(queryClient);
      onClose();
    },
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const epub = Object.fromEntries(new FormData(e.currentTarget as HTMLFormElement));
    save.mutate({ ...epub, kind: name.kind, volume_index: name.index || null, subtitle: name.subtitle } as Schemas["VolumeUpdate"]);
  };
  return (
    <Modal title="Volume details" onClose={onClose} busy={save.isPending} onSubmit={submit}>
      <div className="dlg-head"><h2>Volume details</h2></div>
      <div className="dlg-body">
        <VolumeNameFields value={name} onChange={setName} kinds={kinds} />
        {volume.wp_volume_title && (
          <label className="field"><span>WordPress volume name</span>
            <input value={volume.wp_volume_title} readOnly />
            <span className="hint">Fixed after first publish; WordPress finds the volume's pages by it.</span>
          </label>
        )}
        {EPUB_FIELDS.map(([field, label]) => (
          <label key={field} className="field"><span>{label}</span>
            <input name={field} defaultValue={volume[field]}
              placeholder={field === "epub_title"
                ? render(series.volume_title_template_effective,
                  { series: series.title, kind: name.kind, index: name.index || null, subtitle: name.subtitle })
                : undefined} />
          </label>
        ))}
        {save.isError && <p className="error" role="alert">{save.error.message}</p>}
      </div>
      <div className="dlg-foot">
        <button type="button" disabled={save.isPending} onClick={onClose}>Cancel</button>
        <button type="submit" className="primary" disabled={save.isPending}>Save</button>
      </div>
    </Modal>
  );
}

/** The volume's illustrations job: a new one, or one still running from before a reload. */
export function useIllustrations(volume: Volume | null) {
  const [newJob, setNewJob] = useState<number | null>(null);
  const [done, setDone] = useState(false);
  const active = useQuery({
    queryKey: ["jobs", "active", "wp_illustrations", volume?.id], gcTime: 0, enabled: volume !== null,
    queryFn: () => call(api.GET("/jobs", { params: { query: { active: true } } })),
  });
  const jobId = newJob ?? active.data?.find(
    (j) => j.kind === "wp_illustrations" && (j.params as { volume_id?: number } | null)?.volume_id === volume?.id)?.id ?? null;
  const start = useMutation({
    mutationFn: () => call(api.POST("/volumes/{volume_id}/wp/illustrations", { params: { path: { volume_id: volume!.id } } })),
    onSuccess: (job) => { setDone(false); setNewJob(job.id); },
  });
  return { jobId, running: jobId !== null && !done, start, markDone: () => setDone(true) };
}

/** Publishing the volume's illustrations page: the confirm (while `asking`) and the job's progress. */
export function Illustrations({ volume, job, asking, onAsked }: {
  volume: Volume; job: ReturnType<typeof useIllustrations>; asking: boolean; onAsked: () => void;
}) {
  const { jobId, running, start, markDone } = job;
  return (
    <>
      {asking && !running && (
        <ConfirmDialog title="Publish illustrations" confirmLabel="Publish" busy={start.isPending}
          message={`Publish the illustrations of "${volume.label}" to WordPress? An existing illustrations page for this volume will be overwritten.`}
          error={start.error?.message}
          onConfirm={() => start.mutate(undefined, { onSuccess: onAsked })} onClose={() => { start.reset(); onAsked(); }} />
      )}
      {jobId !== null && (
        <JobProgress jobId={jobId} onDone={markDone} outcome={(j) => {
          const r = (j.result ?? {}) as { page_url?: string; created?: boolean };
          return <p>{j.state === "cancelled" ? "Cancelled" : `${r.created ? "Created" : "Updated"} the volume illustrations page`}{" "}
            {r.page_url && <a href={r.page_url} target="_blank" rel="noreferrer">{r.page_url}</a>}</p>;
        }} />
      )}
    </>
  );
}
