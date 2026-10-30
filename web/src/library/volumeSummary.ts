import { wpTag } from "../publish/wpTag";
import { progressOf, type Doc } from "./shelf";

/** What the line above the chapter table says about the volume. */
export interface VolumeSummary {
  chapters: number;
  progress: number;
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
  return { chapters: docs.length, progress: progressOf(docs), posted, scheduled, next };
}

/** "42 chapters · 68% translated · 30 posted · 5 scheduled (next: Nov 2, 18:00)"; the WordPress
 *  parts go when WordPress is not set up. `fmt` renders the next slot in local terms. */
export function summaryText(s: VolumeSummary, wp: boolean, fmt: (iso: string) => string): string {
  const parts = [
    `${s.chapters} ${s.chapters === 1 ? "chapter" : "chapters"}`,
    `${s.progress}% translated`,
  ];
  if (wp) {
    parts.push(`${s.posted} posted`, `${s.scheduled} scheduled`);
    if (s.next !== null) parts[parts.length - 1] += ` (next: ${fmt(s.next)})`;
  }
  return parts.join(" · ");
}
