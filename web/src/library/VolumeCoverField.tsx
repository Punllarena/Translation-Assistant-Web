import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRef, useState, type KeyboardEvent } from "react";
import { api, call } from "../api/client";
import { invalidateLibrary } from "./queries";
import type { Volume } from "./shelf";
import { postForm } from "./upload";

/** The volume's cover in the Volume details dialog: upload, fetch by image address, clear, and
 *  whether it is the series cover. Each action applies at once, apart from the dialog's Save. */
export default function VolumeCoverField({ volume }: { volume: Volume }) {
  const queryClient = useQueryClient();
  const [address, setAddress] = useState("");
  const file = useRef<HTMLInputElement>(null);
  const path = { params: { path: { volume_id: volume.id } } };
  const changed = () => invalidateLibrary(queryClient);
  const upload = useMutation({
    mutationFn: (picked: File) => {
      const form = new FormData();
      form.append("file", picked);
      return postForm(`/volumes/${volume.id}/cover`, form, "PUT");
    },
    onSettled: changed,
  });
  const fetchUrl = useMutation({
    mutationFn: (url: string) => call(api.POST("/volumes/{volume_id}/cover/url", { ...path, body: { url } })),
    onSuccess: () => setAddress(""),
    onSettled: changed,
  });
  const clear = useMutation({
    mutationFn: () => call(api.DELETE("/volumes/{volume_id}/cover", path)),
    onSettled: changed,
  });
  const choose = useMutation({
    mutationFn: (on: boolean) => call(api.PUT("/series/{series_id}/cover-volume", {
      params: { path: { series_id: volume.series_id } }, body: { volume_id: on ? volume.id : null },
    })),
    onSettled: changed,
  });
  const actions = [upload, fetchUrl, clear, choose];
  const busy = actions.some((m) => m.isPending);
  const error = actions.find((m) => m.isError)?.error;
  const reset = () => actions.forEach((m) => m.reset());
  const fetchNow = () => { reset(); if (address.trim()) fetchUrl.mutate(address.trim()); };
  const onKey = (e: KeyboardEvent) => {
    if (e.key === "Enter") { e.preventDefault(); fetchNow(); } // not the dialog's Save
  };
  return (
    <fieldset className="cover-field" aria-busy={busy}>
      <legend>Cover</legend>
      <div className="cover-field-row">
        {volume.cover_id != null
          ? <img className="cover" src={`/api/covers/${volume.cover_id}`} alt="Volume cover" />
          : <span className="cover cover-tile" aria-hidden="true">{volume.label}</span>}
        <div className="cover-field-actions">
          <div className="toolbar">
            <button type="button" disabled={busy} onClick={() => file.current?.click()}>
              {upload.isPending ? "Uploading…" : volume.cover_id != null ? "Replace…" : "Upload…"}
            </button>
            {volume.cover_id != null && (
              <button type="button" disabled={busy} onClick={() => { reset(); clear.mutate(); }}>Clear</button>
            )}
          </div>
          <div className="cover-url">
            <input type="url" value={address} placeholder="https://…/cover.jpg" aria-label="Image address"
              onChange={(e) => setAddress(e.target.value)} onKeyDown={onKey} disabled={busy} />
            <button type="button" disabled={busy || !address.trim()} onClick={fetchNow}>
              {fetchUrl.isPending ? "Fetching…" : "Fetch"}
            </button>
          </div>
          <span className="hint">Paste the image's own address (right-click the picture, Copy image address), not the page's.</span>
          <label className="check">
            <input type="checkbox" checked={volume.is_series_cover} disabled={busy}
              onChange={(e) => { reset(); choose.mutate(e.target.checked); }} /> Use as series cover
          </label>
          <span className="hint">The Library shows it at once; WordPress after chapter 1 is next published.</span>
        </div>
      </div>
      <input ref={file} type="file" hidden accept="image/png,image/jpeg,image/gif,image/webp"
        aria-label="Cover image file" onChange={(e) => {
          const picked = e.target.files?.[0];
          e.target.value = "";
          if (picked) { reset(); upload.mutate(picked); }
        }} />
      {error && <p className="error" role="alert">{error.message}</p>}
    </fieldset>
  );
}
