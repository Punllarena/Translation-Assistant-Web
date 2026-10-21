import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, call } from "../api/client";
import { ConfirmDialog } from "../ui/Dialog";
import { decode, encode, optionLabel, regroupMessage, type HeadingMode, type Marker, type RegroupCounts } from "./headingCopy";
import { invalidateLibrary } from "./queries";
import type { SeriesRow } from "./shelf";

type Choice = { mode: HeadingMode; marker: string };

/** "Volumes from syosetu headings": which headings start a volume. A change previews the
 *  regroup and asks before moving any chapter; nothing to move applies at once. */
export default function HeadingVolumes({ series, markers }: { series: SeriesRow; markers: Marker[] }) {
  const queryClient = useQueryClient();
  const [pending, setPending] = useState<(Choice & { counts: RegroupCounts }) | null>(null);
  const post = (c: Choice, apply: boolean) => call(api.POST("/series/{series_id}/syosetu/volume-headings", {
    params: { path: { series_id: series.id } }, body: { mode: c.mode, marker: c.marker, apply },
  }));
  const apply = useMutation({
    mutationFn: (c: Choice) => post(c, true),
    onSuccess: () => { setPending(null); void invalidateLibrary(queryClient); },
  });
  const preview = useMutation({
    mutationFn: (c: Choice) => post(c, false),
    onSuccess: (counts, c) => {
      if (counts.volumes_created + counts.chapters_moved + counts.volumes_emptied === 0) apply.mutate(c);
      else setPending({ ...c, counts });
    },
  });
  const saved = encode(series.syosetu_volume_mode as HeadingMode, series.syosetu_volume_marker);
  const busy = preview.isPending || apply.isPending;
  const error = preview.error ?? (pending ? null : apply.error);
  return (
    <div className="field">
      <label className="field">
        <span>Volumes from syosetu headings</span>
        <select value={saved} disabled={busy} onChange={(e) => { apply.reset(); preview.mutate(decode(e.target.value)); }}>
          <option value="all">Every heading</option>
          {markers.map((m) => <option key={m.marker} value={encode("marker", m.marker)}>{optionLabel(m)}</option>)}
          <option value="off">Off</option>
        </select>
      </label>
      {error && <p className="error" role="alert">{error.message}</p>}
      {pending && (
        <ConfirmDialog title="Regroup chapters" message={regroupMessage(pending.counts)} confirmLabel="Regroup"
          busy={apply.isPending} error={apply.error?.message ?? null}
          onConfirm={() => apply.mutate(pending)}
          onClose={() => { if (!apply.isPending) { setPending(null); apply.reset(); } }} />
      )}
    </div>
  );
}
