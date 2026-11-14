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
