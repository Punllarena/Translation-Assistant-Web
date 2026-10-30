import type { Doc } from "./shelf";

/** The selection bar's quick picks. Not `Pick`: that is TypeScript's built-in. */
export type QuickPick = "all" | "none" | "untranslated" | "unposted";

export const QUICK_PICKS: QuickPick[] = ["all", "none", "untranslated", "unposted"];

export const QUICK_LABEL: Record<QuickPick, string> = {
  all: "All",
  none: "None",
  untranslated: "Untranslated",
  unposted: "Not posted",
};

/** The ids a quick pick ticks: All is every chapter of the volume (closed blocks too),
 *  Untranslated is progress below 100, Not posted is a chapter WordPress has never seen. */
export function quickPick(docs: Doc[], pick: QuickPick): Set<number> {
  if (pick === "none") return new Set();
  if (pick === "all") return new Set(docs.map((d) => d.id));
  const keep = pick === "untranslated" ? (d: Doc) => d.progress < 100 : (d: Doc) => d.wp_status === "";
  return new Set(docs.filter(keep).map((d) => d.id));
}
