import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { api, call, type Schemas } from "../api/client";
import { Modal } from "../ui/Dialog";
import type { SeriesRow, Volume } from "./shelf";
import VolumeCoverField from "./VolumeCoverField";
import VolumeNameFields, { type VolumeName } from "./VolumeNameFields";
import { render } from "./volumeNames";
import { invalidateLibrary } from "./queries";

const EPUB_FIELDS = [
  ["epub_title", "EPUB title"], ["epub_author", "Author"], ["epub_language", "Language"],
  ["epub_illustrator", "Illustrator"], ["epub_publisher", "Publisher"],
  ["epub_identifier", "Identifier"], ["epub_description", "Description"],
] as const;

/** The volume's cover, title and EPUB metadata, in a dialog. */
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
    save.mutate({ ...epub, kind: name.kind.trim(), volume_index: name.index || null, subtitle: name.subtitle.trim() } as Schemas["VolumeUpdate"]);
  };
  return (
    <Modal title="Volume details" onClose={onClose} busy={save.isPending} onSubmit={submit}>
      <div className="dlg-head"><h2>Volume details</h2></div>
      <div className="dlg-body">
        <VolumeCoverField volume={volume} />
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
