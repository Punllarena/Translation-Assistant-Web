import type { ReactNode } from "react";
import type { SaveState } from "./saveStore";
import { Check } from "../ui/icons";

/** The saved state is a check alone (with its own accessible name); the others keep their words. */
const SAVE_TEXT: Record<SaveState, string> = {
  saved: "Saved", saving: "Saving…", unsaved: "Unsaved changes", error: "Not saved",
};

/** What the small "Aa" says when the server has no dictionary to check against. */
const SPELL_OFF = "Spellcheck needs a dictionary on the server. Words you add still work.";

export interface Crumbs {
  series: { id: number; title: string };
  volume: { id: number | null; label: string };
}

interface Props {
  nav: ReactNode; // left zone: where you are
  tools: ReactNode; // right zone
  translated: number;
  lineCount: number;
  percent: number;
  phrase: string | null;
  save: { state: SaveState; error: string | null };
  unsavedLines: number[]; // 1-based, shown while a save is failing
  permanent?: boolean; // retrying cannot help, so nothing says it is
  onRetry(): void;
  onCopy(): void; // copies the unsaved text out of the tab
  notice?: ReactNode | null; // the transient line, which may carry an action
  waiting?: ReactNode | null; // a queued move out of the chapter, shown beside the notice
  spellAvailable?: boolean;
}

/** "Line 3", "Lines 3, 7", "Lines 3, 7, 9, 12, 20 and 4 more". */
export function linesText(lines: number[]) {
  const shown = lines.slice(0, 5).join(", ");
  const more = lines.length > 5 ? ` and ${lines.length - 5} more` : "";
  return `${lines.length === 1 ? "Line" : "Lines"} ${shown}${more}`;
}

const R = 7;
const ARC = 2 * Math.PI * R;

function Ring({ percent }: { percent: number }) {
  return (
    <svg className="sb-ring" viewBox="0 0 18 18" width="18" height="18" role="img" aria-label={`${percent}% translated`}>
      <circle cx="9" cy="9" r={R} className="sb-ring-track" />
      <circle cx="9" cy="9" r={R} className="sb-ring-fill" transform="rotate(-90 9 9)"
        strokeDasharray={ARC} strokeDashoffset={ARC * (1 - percent / 100)} />
    </svg>
  );
}

export default function StatusBar({
  nav, tools, translated, lineCount, percent, phrase, save, unsavedLines, permanent = false,
  onRetry, onCopy, notice, waiting, spellAvailable = true,
}: Props) {
  return (
    <div className="statusbar">
      <div className="sb-inner">
        <div className="sb-row">
          <div className="sb-place">{nav}</div>
          <div className="sb-centre">
            <div className="sb-pill">
              <Ring percent={percent} />
              <span>{translated} of {lineCount} lines</span>
              {save.state === "saved" ? (
                // One accessible name: the icon is the state, with no hidden duplicate beside it.
                <span className="save-state save-saved" title={SAVE_TEXT.saved} role="img" aria-label={SAVE_TEXT.saved}>
                  <Check />
                </span>
              ) : (
                <span className="save-state">{SAVE_TEXT[save.state]}</span>
              )}
            </div>
            {phrase && <span>{phrase}</span>}
            {notice && (
              <span className={`sb-notice${typeof notice === "string" ? " muted" : ""}`} role="status">{notice}</span>
            )}
            {waiting && <span className="sb-notice muted" role="status">{waiting}</span>}
            {/* The reasons sit in tooltips: the reading group and this indicator, not standing text. */}
            {!spellAvailable && (
              <span className="sb-note muted sb-spell-off" title={SPELL_OFF} role="img" aria-label="Spellcheck unavailable">Aa</span>
            )}
          </div>
          {/* A mouse press on a toggle keeps the caret where it is, so typing carries on. */}
          <div className="sb-tools" onMouseDown={(e) => {
            if ((e.target as Element).closest("button[aria-pressed]")) e.preventDefault();
          }}>{tools}</div>
        </div>
        {/* Its own row, so a long message never squeezes the chapter title; it stays put
            across attempts instead of being torn down and announced again. */}
        {save.error !== null && (
          <div className="sb-alert">
            <span role="alert" className="error">
              {unsavedLines.length > 0 && `${linesText(unsavedLines)} not saved: `}
              {save.error}{!permanent && " Retrying…"}
            </span>
            <button type="button" className="small" onClick={onRetry}>Retry</button>
            <button type="button" className="small" onClick={onCopy}>Copy unsaved text</button>
          </div>
        )}
      </div>
    </div>
  );
}
