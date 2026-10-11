import type { ReactNode } from "react";
import { Link } from "react-router";
import type { SaveState } from "./saveStore";

const SAVE_TEXT: Record<SaveState, string> = {
  saved: "Saved", saving: "Saving…", unsaved: "Unsaved changes", error: "Not saved",
};

interface Props {
  title: string;
  line: number; // 1-based
  total: number;
  percent: number;
  words: number;
  phrase: string | null;
  save: { state: SaveState; error: string | null };
  onRetry(): void;
  notice?: string | null;
  extra?: ReactNode; // later tasks add controls here
}

export default function StatusBar({ title, line, total, percent, words, phrase, save, onRetry, notice, extra }: Props) {
  return (
    <div className="statusbar">
      <Link to="/">Library</Link>
      <strong>{title}</strong>
      <span>Line {line}/{total}</span>
      <span>{percent}%</span>
      <span>{words.toLocaleString()} words</span>
      {phrase && <span>{phrase}</span>}
      <span className={save.state === "saved" ? "save-state muted" : "save-state"}>{SAVE_TEXT[save.state]}</span>
      {save.state === "error" && <span role="alert" className="error">{save.error}</span>}
      {save.state === "error" && <button onClick={onRetry}>Retry</button>}
      {notice && <span className="muted">{notice}</span>}
      {extra}
    </div>
  );
}
