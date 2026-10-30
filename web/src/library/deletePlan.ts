import type { Doc } from "./shelf";

/** What deleting the chosen chapters does about their images. */
export interface DeletePlan {
  /** Chapters holding at least one image. */
  withImages: number;
  /** Those whose images can move to their volume's Illustrations chapter. */
  movable: number;
  /** Those whose images go with the chapter (loose, syosetu, or the Illustrations chapter). */
  stuck: number;
  images: number;
}

/** One rule for the single and the multi-chapter delete dialog; `move` is only offered when
 *  something can move. */
export function deletePlan(docs: Doc[], syosetu: boolean): DeletePlan {
  let withImages = 0;
  let movable = 0;
  let images = 0;
  for (const doc of docs) {
    if (doc.image_count === 0) continue;
    withImages += 1;
    images += doc.image_count;
    if (doc.volume_id !== null && !syosetu && !doc.is_illustrations) movable += 1;
  }
  return { withImages, movable, stuck: withImages - movable, images };
}

/** Whether this chapter's images would be moved rather than dropped. */
export const canMoveImages = (doc: Doc, syosetu: boolean) =>
  doc.image_count > 0 && doc.volume_id !== null && !syosetu && !doc.is_illustrations;
