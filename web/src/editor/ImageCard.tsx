import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, call } from "../api/client";
import type { Image } from "./rows";

/** An illustration between lines (desktop card_list.ImageCard): collapse toggle, cover
 *  marker, include-in-export checkbox. Not a line: no navigation, spellcheck or progress. */
export default function ImageCard({ image, collapsed }: { image: Image; collapsed: boolean }) {
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
        {image.is_cover && <span className="badge">Cover</span>}
        <label>
          <input type="checkbox" checked={!image.exclude_export} disabled={toggle.isPending}
            onChange={(e) => toggle.mutate(!e.target.checked)} /> Include in export
        </label>
        {toggle.isError && <span className="error">{toggle.error.message}</span>}
      </figcaption>
      {open && <img src={`/api/images/${image.id}`} alt={image.src_path} loading="lazy" />}
    </figure>
  );
}
