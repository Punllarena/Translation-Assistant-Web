const TAGS: Record<string, string> = { publish: "pub", future: "sched" };

/** The picker's WordPress cell: tag plus local "MM/DD HH:MM" (desktop _fmt_wp_date). */
export function wpBadge(doc: { wp_status: string; wp_published_at: string | null }): string {
  const tag = TAGS[doc.wp_status] ?? "";
  if (!tag || !doc.wp_published_at) return tag;
  const d = new Date(doc.wp_published_at);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${tag} ${p(d.getMonth() + 1)}/${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}
