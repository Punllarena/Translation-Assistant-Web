import { wpTag } from "../publish/wpTag";
import type { Doc } from "./shelf";

/** What the line above the chapter table adds to the volume header: the WordPress counts only.
 *  The chapter count and the translated percent live in the header, so they are not repeated. */
export interface VolumeSummary {
  /** Published, plus a schedule whose time has passed (the "Published?" tag). */
  posted: number;
  scheduled: number;
  /** The earliest scheduled time still ahead, ISO; null when nothing is scheduled. */
  next: string | null;
}

/** Counts come from the cached `wp_status` — the tag's own rule, so "Published?" counts as posted. */
export function volumeSummary(docs: Doc[], now: Date): VolumeSummary {
  let posted = 0;
  let scheduled = 0;
  let next: string | null = null;
  for (const doc of docs) {
    const tag = wpTag(doc, now);
    if (tag === "published" || tag === "due") posted += 1;
    if (tag !== "scheduled") continue;
    scheduled += 1;
    const at = doc.wp_scheduled_for ?? doc.wp_published_at;
    if (at !== null && (next === null || at < next)) next = at;
  }
  return { posted, scheduled, next };
}

/** "30 posted · 5 scheduled (next: Nov 2, 18:00)"; empty without WordPress, so the caller can
 *  render no line at all. `fmt` renders the next slot in local terms. */
export function summaryText(s: VolumeSummary, wp: boolean, fmt: (iso: string) => string): string {
  if (!wp) return "";
  const parts = [`${s.posted} posted`, `${s.scheduled} scheduled`];
  if (s.next !== null) parts[parts.length - 1] += ` (next: ${fmt(s.next)})`;
  return parts.join(" · ");
}
