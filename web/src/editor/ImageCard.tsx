import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, call } from "../api/client";
import { Modal } from "../ui/Dialog";
import { shownTitle, type Doc } from "../library/shelf";
import { anchorFromCardNumber, cardNumberFromAnchor } from "./imageMove";
import type { Image } from "./rows";

/** An illustration between lines (desktop card_list.ImageCard): collapse toggle and
 *  include-in-export checkbox. Not a line: no navigation, spellcheck or progress. */
export default function ImageCard({ image, collapsed, chapters, lineCount }: {
  image: Image; collapsed: boolean; chapters: Doc[]; lineCount: number;
}) {
  const [moving, setMoving] = useState(false);
  const [open, setOpen] = useState(!collapsed);
  useEffect(() => setOpen(!collapsed), [collapsed]);
  const queryClient = useQueryClient();
  const toggle = useMutation({
    mutationFn: (exclude: boolean) =>
      call(api.PATCH("/images/{image_id}", { params: { path: { image_id: image.id } }, body: { exclude_export: exclude } })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["document", image.document_id, "images"] }),
  });
  return (
    <figure className="image-card">
      <figcaption className="toolbar">
        <button aria-expanded={open} onClick={() => setOpen(!open)}>{open ? "▾" : "▸"} Image</button>
        <label>
          <input type="checkbox" checked={!image.exclude_export} disabled={toggle.isPending}
            onChange={(e) => toggle.mutate(!e.target.checked)} /> Include in export
        </label>
        <button type="button" onClick={() => setMoving(true)}>Move…</button>
        {toggle.isError && <span className="error">{toggle.error.message}</span>}
      </figcaption>
      {open && <img src={`/api/images/${image.id}`} alt={image.src_path} loading="lazy" />}
      {moving && <MoveDialog image={image} chapters={chapters} lineCount={lineCount} onClose={() => setMoving(false)} />}
    </figure>
  );
}

function MoveDialog({ image, chapters, lineCount, onClose }: {
  image: Image; chapters: Doc[]; lineCount: number; onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [chapter, setChapter] = useState(image.document_id);
  const [before, setBefore] = useState(cardNumberFromAnchor(image.anchor_position, lineCount));
  const move = useMutation({
    mutationFn: () => call(api.PATCH("/images/{image_id}", {
      params: { path: { image_id: image.id } },
      body: { anchor_position: anchorFromCardNumber(before), ...(chapter !== image.document_id && { document_id: chapter }) },
    })),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["document"] });
      await queryClient.invalidateQueries({ queryKey: ["documents"] });
      onClose();
    },
  });
  const here = chapter === image.document_id;
  return (
    <Modal title="Move image" onClose={onClose} busy={move.isPending}
      onSubmit={(e) => { e.preventDefault(); if (!move.isPending) move.mutate(); }}>
      <div className="dlg-head"><h2>Move image</h2></div>
      <div className="dlg-body">
        <label className="field"><span>Chapter</span>
          <select value={chapter} onChange={(e) => setChapter(Number(e.target.value))}>
            {chapters.map((d) => <option key={d.id} value={d.id}>{shownTitle(d)}</option>)}
          </select>
        </label>
        <label className="field"><span>Before line</span>
          <input inputMode="numeric" value={before} placeholder="end of chapter"
            onChange={(e) => setBefore(e.target.value)} />
        </label>
        {!here && <p className="hint">The image leaves this chapter.</p>}
        {move.isError && <p className="error" role="alert">{move.error.message}</p>}
      </div>
      <div className="dlg-foot">
        <button type="button" disabled={move.isPending} onClick={onClose}>Cancel</button>
        <button type="submit" className="primary" disabled={move.isPending}>Move</button>
      </div>
    </Modal>
  );
}
