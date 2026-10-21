import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { api, call } from "../api/client";
import { Modal } from "../ui/Dialog";
import { invalidateLibrary } from "./queries";
import type { Volume } from "./shelf";

/** Merge the ticked volumes into one: the kept volume's name and details stay, the others go. */
export default function MergeVolumesDialog({ seriesId, volumes, onClose, onMerged }: {
  seriesId: number; volumes: Volume[]; onClose: () => void; onMerged: (id: number) => void;
}) {
  const queryClient = useQueryClient();
  const [into, setInto] = useState(volumes[0].id);
  const merge = useMutation({
    mutationFn: () => call(api.POST("/series/{series_id}/volumes/merge", {
      params: { path: { series_id: seriesId } }, body: { volume_ids: volumes.map((v) => v.id), into },
    })),
    onSuccess: async (kept) => { await invalidateLibrary(queryClient); onMerged(kept.id); },
  });
  const submit = (e: FormEvent) => { e.preventDefault(); merge.mutate(); };
  const others = volumes.length - 1;
  return (
    <Modal title={`Merge ${volumes.length} volumes`} onClose={onClose} onSubmit={submit} busy={merge.isPending}>
      <div className="dlg-head"><h2>Merge {volumes.length} volumes</h2></div>
      <div className="dlg-body">
        <fieldset className="stack">
          <legend>Keep the name and details of:</legend>
          {volumes.map((v) => (
            <label key={v.id}>
              <input type="radio" name="into" checked={into === v.id} onChange={() => setInto(v.id)} /> {v.label}
            </label>
          ))}
        </fieldset>
        <p className="muted">The other {others} {others === 1 ? "volume is" : "volumes are"} deleted; their chapters move into it.</p>
        {merge.isError && <p className="error" role="alert">{merge.error.message}</p>}
      </div>
      <div className="dlg-foot">
        <button type="button" disabled={merge.isPending} onClick={onClose}>Cancel</button>
        <button type="submit" className="primary" disabled={merge.isPending}>Merge</button>
      </div>
    </Modal>
  );
}
