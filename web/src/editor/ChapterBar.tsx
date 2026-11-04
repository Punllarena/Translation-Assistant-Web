import type { MouseEvent } from "react";
import { Link } from "react-router";
import Menu from "../ui/Menu";
import { shownTitle, type Doc } from "../library/shelf";
import type { Crumbs } from "./StatusBar";

const label = (d: Doc) => (d.chapter_number != null ? `Ch. ${d.chapter_number}` : "");

/** Previous / next chapter buttons and the list of the chapter's volume. The menu also
 *  holds the way back (Library / series / volume), so the sticky top stays one row. */
export default function ChapterNav({ doc, chapters, crumbs, onGo, onLeave, prevKey, nextKey }: {
  doc: Doc; chapters: { prev: Doc | null; next: Doc | null; volume: Doc[] }; crumbs: Crumbs;
  onGo: (d: Doc) => void; onLeave: (to: string) => void;
  prevKey: string; nextKey: string;
}) {
  const { prev, next, volume } = chapters;
  const { series, volume: at } = crumbs;
  // A plain left click leaves through onLeave; modified clicks keep the link's own behaviour.
  const crumb = (close: () => void, to: string, text: string) => (
    <Link to={to} role="menuitem" onClick={(e: MouseEvent) => {
      if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      e.preventDefault();
      close();
      onLeave(to);
    }}>{text}</Link>
  );
  return (
    <span className="chapter-nav">
      <button type="button" className="quiet" aria-label="Previous chapter" title={`Previous chapter (${prevKey})`} disabled={!prev}
        onClick={() => prev && onGo(prev)}>‹</button>
      <Menu align="start" buttonLabel={`${[label(doc), shownTitle(doc)].filter(Boolean).join(" ")}, chapter list`}
        label={<>
          {label(doc) && <span className="ch-num">{label(doc)}</span>}
          <span className="ch-title">{shownTitle(doc)}</span>
          <span aria-hidden="true">▾</span>
        </>}>
        {(close) => (
          <>
            <nav aria-label="Breadcrumb" className="sb-crumbs">
              {crumb(close, "/", "Library")}
              <span aria-hidden="true">/</span>
              {crumb(close, `/series/${series.id}`, series.title)}
              <span aria-hidden="true">/</span>
              {crumb(close, `/series/${series.id}?tab=volumes&volume=${at.id ?? "none"}`, at.id == null ? "No volume" : at.label)}
            </nav>
            <div className="menu-sep" role="presentation" />
            {volume.map((d) => (
              <button key={d.id} type="button" role="menuitemradio" aria-checked={d.id === doc.id}
                title={shownTitle(d)} onClick={() => { close(); if (d.id !== doc.id) onGo(d); }}>
                <span className="ch-row-title">{d.chapter_number != null ? `${d.chapter_number} · ` : ""}{shownTitle(d)}</span>
                <span className="muted ch-progress">{d.progress}%</span>
              </button>
            ))}
          </>
        )}
      </Menu>
      <button type="button" className="quiet" aria-label="Next chapter" title={`Next chapter (${nextKey})`} disabled={!next}
        onClick={() => next && onGo(next)}>›</button>
    </span>
  );
}
