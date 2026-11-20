type NightlyFields = { syosetu_url: string; status: string; archived_at: string | null; syosetu_nightly: boolean };

/** Why the nightly syosetu check skips this series; null when it is in the pass, or has no
 * syosetu URL (the caller hides the section then). Switched off wins over the other reasons. */
export function nightlyNote(s: NightlyFields): string | null {
  if (!s.syosetu_url) return null;
  if (!s.syosetu_nightly) return "Off for this series.";
  if (s.status !== "ongoing") return "Skipped: the series is not Ongoing.";
  if (s.archived_at) return "Skipped: the series is archived.";
  return null;
}

type RunSeries = { series_id: number; new_chapters: number };
type DocLite = { id: number; series_id: number; series_order: number; line_count: number; translated_count: number };
export type NightlyBadge = { newChapters: number; href: string };

/** "+N new" badges from the latest nightly run: N is what that run queued, and the link is the
 * series' first chapter (by series_order) with an untranslated line, else the series page. */
export function newChapterBadges(run: { series: RunSeries[] } | undefined, docs: DocLite[]): Map<number, NightlyBadge> {
  const out = new Map<number, NightlyBadge>();
  for (const s of run?.series ?? []) {
    if (s.new_chapters <= 0) continue;
    const first = docs
      .filter((d) => d.series_id === s.series_id && d.translated_count < d.line_count)
      .sort((a, b) => a.series_order - b.series_order || a.id - b.id)[0];
    out.set(s.series_id, { newChapters: s.new_chapters, href: first ? `/documents/${first.id}` : `/series/${s.series_id}` });
  }
  return out;
}
