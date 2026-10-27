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
  line: number; // 1-based
  total: number;
  translated: number;
  lineCount: number;
  percent: number;
  words: number;
  phrase: string | null;
  save: { state: SaveState; error: string | null };
  onRetry(): void;
  notice?: string | null;
  spellAvailable?: boolean;
  onLeave(to: string): void; // leaves through the save flush
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
  crumbs, nav, tools, line, total, translated, lineCount, percent, words, phrase, save, onRetry, notice,
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
          <div className="sb-pill" role="status">
            <Ring percent={percent} />
            <span>{translated} of {lineCount} lines</span>
            <span>{words.toLocaleString()} words</span>
            <span className="sb-line" title={`Line ${line} of ${total}`}>at L{line}</span>
            <span className={save.state === "saved" ? "save-state muted" : "save-state"}>{SAVE_TEXT[save.state]}</span>
          </div>
          {save.state === "error" && <span role="alert" className="error">{save.error}</span>}
          {save.state === "error" && <button type="button" className="small" onClick={onRetry}>Retry</button>}
          {phrase && <span>{phrase}</span>}
          {notice && <span className="muted">{notice}</span>}
          {!spellAvailable && <span className="muted">Spellcheck unavailable</span>}
        </div>
        <div className="sb-tools">{tools}</div>
      </div>
    </div>
  );
}
