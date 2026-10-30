import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api, call } from "../../api/client";
import type { Doc } from "../shelf";
import { invalidateLibrary } from "../queries";
import { ConfirmDialog } from "../../ui/Dialog";
import { imageActions, imageSrc, type GalleryImage } from "./galleryGroups";

/** One gallery image, full size, with previous/next and the actions it allows — never an
 *  "open in editor". The dialog is native and modal; Esc closes it. */
export default function ImageViewer({ image, doc, seriesId, syosetu, images, index, onClose, onStep }: {
  image: GalleryImage;
  doc: Doc | undefined;
  seriesId: number;
  syosetu: boolean;
  images: GalleryImage[];
  index: number;
  onClose: () => void;
  onStep: (delta: number) => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  useEffect(() => { const d = ref.current; if (d && !d.open) d.showModal(); }, []);
  const allowed = imageActions(image, doc, syosetu);
  // Deleting it empties the Illustrations chapter, which goes too.
  const last = doc?.is_illustrations === true
    && images.filter((i) => i.kind === "image" && i.document_id === doc.id).length === 1;
  const done = async () => {
    await invalidateLibrary(queryClient);
    await queryClient.invalidateQueries({ queryKey: ["gallery", seriesId] });
    onClose();
  };
  const fail = (e: Error) => setError(e.message);
  const cover = useMutation({
    mutationFn: () => call(api.POST("/images/{image_id}/cover", {
      params: { path: { image_id: image.id } } })),
    onSuccess: done, onError: fail,
  });
  const move = useMutation({
    mutationFn: () => call(api.POST("/images/{image_id}/move", {
      params: { path: { image_id: image.id } } })),
    onSuccess: done, onError: fail,
  });
  const remove = useMutation({
    mutationFn: () => call(api.DELETE("/images/{image_id}", {
      params: { path: { image_id: image.id } } })),
    onSuccess: done, onError: fail,
  });
  const busy = cover.isPending || move.isPending || remove.isPending;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (confirming) return; // the dialog on top owns the keys
      if (e.key === "ArrowLeft") onStep(-1);
      else if (e.key === "ArrowRight") onStep(1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [confirming, onStep]);
  const act = (run: () => void) => { setError(null); run(); };
  return (
    <>
      <dialog ref={ref} className="dlg gallery-viewer" aria-label={`Image ${image.src_path}`}
        onClose={onClose} onCancel={(e) => { if (busy) e.preventDefault(); }}>
        <div className="dlg-head">
          <h2>{image.src_path}</h2>
          <p className="muted">
            {image.kind === "cover" ? "Volume cover" : doc ? doc.chapter_title || doc.title : ""}
          </p>
        </div>
        <div className="dlg-body gallery-viewer-body">
          <img src={imageSrc(image)} alt={image.src_path} />
          {error && <p className="error" role="alert">{error}</p>}
          <div className="gallery-viewer-nav">
            <button type="button" disabled={index <= 0} onClick={() => onStep(-1)}>Previous</button>
            <span className="muted">{index + 1} of {images.length}</span>
            <button type="button" disabled={index >= images.length - 1} onClick={() => onStep(1)}>Next</button>
          </div>
          {allowed.remove && (
            <div className="toolbar">
              {allowed.cover && (
                <button type="button" disabled={busy} onClick={() => act(() => cover.mutate())}>
                  Set as volume cover
                </button>
              )}
              {allowed.move && (
                <button type="button" disabled={busy} onClick={() => act(() => move.mutate())}>
                  Move to Illustrations
                </button>
              )}
              <button type="button" className="danger" disabled={busy}
                onClick={() => act(() => setConfirming(true))}>Delete</button>
            </div>
          )}
        </div>
      </dialog>
      {confirming && (
        <ConfirmDialog title="Delete image" confirmLabel="Delete" danger
          busy={remove.isPending} error={error}
          message={<>
            Delete {image.src_path}? It is removed from its chapter.
            {last && <p>This is the last image; the Illustrations chapter will be deleted too.</p>}
          </>}
          onConfirm={() => act(() => remove.mutate())} onClose={() => setConfirming(false)} />
      )}
    </>
  );
}
