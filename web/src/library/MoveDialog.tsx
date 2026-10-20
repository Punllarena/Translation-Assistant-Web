import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { api, call } from "../api/client";
import { Modal } from "../ui/Dialog";
import { byVolumeOrder } from "./shelf";
import { invalidateLibrary, useAllVolumes, useSeriesList } from "./queries";

/** Move chapters to a volume of this series, or to another series (and optionally a volume there).
 *  Within the series the server appends them to the end of the volume. */
export default function MoveDialog({ ids, currentSeriesId, onClose, onMoved }: {
  ids: number[]; currentSeriesId: number; onClose: () => void; onMoved?: () => void;
}) {
  const queryClient = useQueryClient();
  const series = useSeriesList();
  const volumes = useAllVolumes();
  const [seriesId, setSeriesId] = useState(currentSeriesId);
  const [volume, setVolume] = useState("none");
  const options = (volumes.data ?? []).filter((v) => v.series_id === seriesId).sort(byVolumeOrder);
  const move = useMutation({
    mutationFn: async () => {
      const volumeId = volume === "none" ? null : Number(volume);
      const patch = (id: number, body: { series_id?: number; volume_id: number | null }) =>
        call(api.PATCH("/documents/{document_id}", { params: { path: { document_id: id } }, body }));
      if (seriesId !== currentSeriesId) {
        for (const id of ids) await patch(id, { series_id: seriesId, volume_id: volumeId });
      } else if (volumeId !== null) {
        await call(api.POST("/volumes/{volume_id}/documents", {
          params: { path: { volume_id: volumeId } }, body: { document_ids: ids },
        }));
      } else {
        for (const id of ids) await patch(id, { volume_id: null });
      }
    },
    onSettled: () => invalidateLibrary(queryClient),
    onSuccess: () => { onMoved?.(); onClose(); },
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!move.isPending) move.mutate();
  };
  const title = ids.length === 1 ? "Move chapter" : `Move ${ids.length} chapters`;
  const loadError = series.error ?? volumes.error;
  return (
    <Modal title={title} onClose={onClose} busy={move.isPending} onSubmit={submit}>
      <div className="dlg-head"><h2>{title}</h2></div>
      <div className="dlg-body">
        <label className="field"><span>Series</span>
          <select value={seriesId} onChange={(e) => { setSeriesId(Number(e.target.value)); setVolume("none"); }}>
            {(series.data ?? []).map((s) => <option key={s.id} value={s.id}>{s.title}</option>)}
          </select>
        </label>
        <label className="field"><span>Volume</span>
          <select value={volume} onChange={(e) => setVolume(e.target.value)}>
            {options.map((v) => <option key={v.id} value={v.id}>{v.title}</option>)}
            <option value="none">No volume</option>
          </select>
        </label>
        {loadError && <p className="error" role="alert">{loadError.message}</p>}
        {move.isError && <p className="error" role="alert">{move.error.message}</p>}
      </div>
      <div className="dlg-foot">
        <button type="button" disabled={move.isPending} onClick={onClose}>Cancel</button>
        <button type="submit" className="primary" disabled={move.isPending || !series.data}>Move</button>
      </div>
    </Modal>
  );
}
