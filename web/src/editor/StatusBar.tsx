import type { MouseEvent, ReactNode } from "react";
import { Link } from "react-router";
import type { SaveState } from "./saveStore";

const SAVE_TEXT: Record<SaveState, string> = {
  saved: "Saved", saving: "Saving…", unsaved: "Unsaved changes", error: "Not saved",
};

export interface Crumbs {
  series: { id: number; title: string };
  volume: { id: number | null; label: string };
}

interface Props {
  crumbs: Crumbs;
  nav: ReactNode; // left zone: where you are
  tools: ReactNode; // right zone
  line: number | null; // 1-based; null in a chapter with no lines
  total: number;
  translated: number;
  lineCount: number;
  percent: number;
  words: number;
  phrase: string | null;
  save: { state: SaveState; error: string | null };
  unsavedLines: number[]; // 1-based, shown while a save is failing
  onRetry(): void;
  notice?: string | null;
  spellAvailable?: boolean;
  onLeave(to: string): void; // leaves through the save flush
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
  crumbs, nav, tools, line, total, translated, lineCount, percent, words, phrase, save, unsavedLines, onRetry, notice,
  spellAvailable = true, onLeave,
}: Props) {
  const { series, volume } = crumbs;
  // A plain left click leaves through onLeave; modified clicks keep the link's own behaviour (new tab, ...).
  const crumb = (to: string, text: string) => (
    <Link to={to} onClick={(e: MouseEvent) => {
      if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      e.preventDefault();
      onLeave(to);
    }}>{text}</Link>
  );
  return (
    <div className="statusbar">
      <nav aria-label="Breadcrumb" className="sb-crumbs">
        {crumb("/", "Library")}
        <span aria-hidden="true">/</span>
        {crumb(`/series/${series.id}`, series.title)}
        <span aria-hidden="true">/</span>
        {crumb(`/series/${series.id}?tab=volumes&volume=${volume.id ?? "none"}`, volume.id == null ? "No volume" : volume.label)}
      </nav>
      <div className="sb-row">
        <div className="sb-place">{nav}</div>
        <div className="sb-centre">
          <div className="sb-pill">
            <Ring percent={percent} />
            <span>{translated} of {lineCount} lines</span>
            <span>{words.toLocaleString()} words</span>
            {line != null && <span className="sb-line" title={`Line ${line} of ${total}`}>at L{line}</span>}
            <span className={save.state === "saved" ? "save-state muted" : "save-state"}>{SAVE_TEXT[save.state]}</span>
          </div>
          {save.state === "error" && <span role="alert" className="error">{linesText(unsavedLines)} not saved: {save.error} Retrying…</span>}
          {save.state === "error" && <button type="button" className="small" onClick={onRetry}>Retry</button>}
          {phrase && <span>{phrase}</span>}
          {notice && <span className="muted" role="status">{notice}</span>}
          {!spellAvailable && <span className="muted">Spellcheck unavailable</span>}
        </div>
        {/* A mouse press on a toggle keeps the caret where it is, so typing carries on. */}
        <div className="sb-tools" onMouseDown={(e) => {
          if ((e.target as Element).closest("button[aria-pressed]")) e.preventDefault();
        }}>{tools}</div>
      </div>
    </div>
  );
}
