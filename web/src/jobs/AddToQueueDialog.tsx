import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { api, call } from "../api/client";
import { useAllVolumes, useDocuments, useSeriesList } from "../library/queries";
import { byVolumeOrder } from "../library/shelf";
import { Modal } from "../ui/Dialog";
import ChapterPicker from "./ChapterPicker";

export const QUEUE_KEY = ["ollama", "queue"] as const;

type Scope = "series" | "volume" | "documents";

/** Queue a whole series (a standing order), one of its volumes, or ticked chapters. */
export default function AddToQueueDialog({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const series = useSeriesList();
  const volumes = useAllVolumes();
  const docs = useDocuments();
  const [seriesId, setSeriesId] = useState<number | null>(null);
  const [scope, setScope] = useState<Scope>("series");
  const [volumeId, setVolumeId] = useState<number | null>(null);
  const [picked, setPicked] = useState<Set<number>>(new Set());
  const current = seriesId ?? series.data?.[0]?.id ?? null;
  const volumeOptions = (volumes.data ?? []).filter((v) => v.series_id === current).sort(byVolumeOrder);
  const syosetu = series.data?.find((s) => s.id === current)?.source === "syosetu";
  const volume = volumeId !== null && volumeOptions.some((v) => v.id === volumeId) ? volumeId : volumeOptions[0]?.id ?? null;
  const ready = current !== null && (scope === "series" || (scope === "volume" ? volume !== null : picked.size > 0));
  const add = useMutation({
    mutationFn: () => call(api.POST("/ollama/queue", {
      body: {
        kind: scope, series_id: current!,
        volume_id: scope === "volume" ? volume : null,
        document_ids: scope === "documents" ? [...picked] : [],
      },
    })),
    onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: QUEUE_KEY }); onClose(); },
  });
  const submit = (e: FormEvent) => { e.preventDefault(); if (ready && !add.isPending) add.mutate(); };
  const loadError = series.error ?? volumes.error ?? docs.error;
  return (
    <Modal title="Add to the Ollama queue" onClose={onClose} busy={add.isPending} onSubmit={submit}>
      <div className="dlg-head"><h2>Add to the Ollama queue</h2></div>
      <div className="dlg-body">
        <label className="field"><span>Series</span>
          <select value={current ?? ""} onChange={(e) => { setSeriesId(Number(e.target.value)); setVolumeId(null); setPicked(new Set()); }}>
            {(series.data ?? []).map((s) => <option key={s.id} value={s.id}>{s.title}</option>)}
          </select>
        </label>
        <div className="seg" role="group" aria-label="What to queue">
          <button type="button" aria-pressed={scope === "series"} onClick={() => setScope("series")}>Whole series</button>
          <button type="button" aria-pressed={scope === "volume"} onClick={() => setScope("volume")}>A volume</button>
          <button type="button" aria-pressed={scope === "documents"} onClick={() => setScope("documents")}>Chapters</button>
        </div>
        {scope === "series" && <p className="hint">A standing order: chapters added to the series later are picked up too.</p>}
        {scope === "volume" && (
          <label className="field"><span>Volume</span>
            <select value={volume ?? ""} onChange={(e) => setVolumeId(Number(e.target.value))}>
              {volumeOptions.map((v) => <option key={v.id} value={v.id}>{v.label}</option>)}
            </select>
            {volumeOptions.length === 0 && <span className="hint">This series has no volumes.</span>}
          </label>
        )}
        {scope === "documents" && current !== null && (
          <ChapterPicker seriesId={current} docs={docs.data ?? []} volumes={volumes.data ?? []} syosetu={syosetu}
            picked={picked} onChange={setPicked} />
        )}
        {loadError && <p className="error" role="alert">{loadError.message}</p>}
        {add.isError && <p className="error" role="alert">{add.error.message}</p>}
      </div>
      <div className="dlg-foot">
        <button type="button" disabled={add.isPending} onClick={onClose}>Cancel</button>
        <button type="submit" className="primary" disabled={!ready || add.isPending}>Add</button>
      </div>
    </Modal>
  );
}
