import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, call } from "../api/client";
import { ConfirmDialog } from "../ui/Dialog";
import { invalidateLibrary } from "./queries";
import { canMoveImages, deletePlan } from "./deletePlan";
import type { Doc } from "./shelf";

/** Delete one or more chapters. When any holds images it asks what happens to them: move them to
 *  the volume's Illustrations chapter (only the chapters that can), or delete them. One request
 *  per chapter, as before; a failure stops the run and shows its message. */
export default function DeleteChaptersDialog({ docs, syosetu, onDone, onClose }: {
  docs: Doc[]; syosetu: boolean; onDone: () => void; onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const plan = deletePlan(docs, syosetu);
  const [choice, setChoice] = useState<"move" | "delete">(plan.movable > 0 ? "move" : "delete");
  const n = docs.length;
  const remove = useMutation({
    mutationFn: async () => {
      for (const doc of docs) {
        const images = choice === "move" && canMoveImages(doc, syosetu) ? "move" : "delete";
        await call(api.DELETE("/documents/{document_id}", {
          params: { path: { document_id: doc.id }, query: { images } },
        }));
      }
    },
    onSettled: () => invalidateLibrary(queryClient), // a partial failure still changed the list
    onSuccess: () => { onDone(); onClose(); },
  });
  return (
    <ConfirmDialog title={n === 1 ? "Delete chapter" : "Delete chapters"} confirmLabel="Delete" danger
      busy={remove.isPending} error={remove.error?.message} onConfirm={() => remove.mutate()} onClose={onClose}
      message={
        <>
          <p>Delete {n === 1 ? "this chapter" : `${n} chapters`}? This can't be undone.</p>
          {plan.withImages > 0 && (
            <div className="delete-images">
              {plan.movable > 0 && (
                <label className="check">
                  <input type="radio" name="delete-images" checked={choice === "move"}
                    onChange={() => setChoice("move")} />
                  <span>Move their images to the volume's Illustrations chapter</span>
                </label>
              )}
              <label className="check">
                <input type="radio" name="delete-images" checked={choice === "delete"}
                  onChange={() => setChoice("delete")} />
                <span>Delete the images too</span>
              </label>
              {plan.stuck > 0 && (
                <p className="muted">
                  {plan.stuck === 1 ? "1 chapter is" : `${plan.stuck} chapters are`} outside a volume or
                  in a syosetu series; their images will be deleted.
                </p>
              )}
            </div>
          )}
        </>
      } />
  );
}
