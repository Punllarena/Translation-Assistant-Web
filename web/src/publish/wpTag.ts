import type { Doc } from "../library/shelf";

/** What the stored WordPress state means now (spec §2). */
export type WpTag = "published" | "scheduled" | "due" | "none";

export const WP_TAG_LABEL: Record<WpTag, string> = {
  published: "Published",
  scheduled: "Scheduled",
  due: "Published?",
  none: "Not posted",
};

/** `future` whose scheduled time (else posted time) has passed reads "Published?"; the tag is
 *  only as fresh as ta-web's stored copy until the user checks it. Never throws on a missing
 *  date: an older `future` row with neither keeps saying Scheduled. */
export function wpTag(
  doc: Pick<Doc, "wp_status" | "wp_scheduled_for" | "wp_published_at">,
  now: Date,
): WpTag {
  if (doc.wp_status === "publish") return "published";
  if (doc.wp_status !== "future") return "none";
  const at = doc.wp_scheduled_for ?? doc.wp_published_at;
  if (at === null) return "scheduled";
  return new Date(at) <= now ? "due" : "scheduled";
}

export function wpTagTone(tag: WpTag): "ok" | "warn" | "muted" | "" {
  if (tag === "published") return "ok";
  if (tag === "scheduled") return "warn";
  if (tag === "due") return "muted";
  return "";
}

/** The chapter menu's publish item, and the tag popover's action. */
export function menuPublishLabel(tag: WpTag): "Publish…" | "Reschedule…" | "Update post…" {
  if (tag === "scheduled") return "Reschedule…";
  if (tag === "published" || tag === "due") return "Update post…";
  return "Publish…";
}
