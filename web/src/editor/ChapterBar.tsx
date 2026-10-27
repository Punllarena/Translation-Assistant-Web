import Menu from "../ui/Menu";
import { shownTitle, type Doc } from "../library/shelf";

const label = (d: Doc) => (d.chapter_number != null ? `Ch. ${d.chapter_number}` : "");

/** Previous / next chapter buttons and the list of the chapter's volume. */
export default function ChapterNav({ doc, chapters, onGo }: {
  doc: Doc; chapters: { prev: Doc | null; next: Doc | null; volume: Doc[] }; onGo: (d: Doc) => void;
}) {
  const { prev, next, volume } = chapters;
  return (
    <span className="chapter-nav">
      <button type="button" className="quiet" aria-label="Previous chapter" disabled={!prev}
        onClick={() => prev && onGo(prev)}>‹</button>
      <Menu align="start" buttonLabel={`${[label(doc), shownTitle(doc)].filter(Boolean).join(" ")}, chapter list`}
        label={<>
          {label(doc) && <span className="ch-num">{label(doc)}</span>}
          <span className="ch-title">{shownTitle(doc)}</span>
          <span aria-hidden="true">▾</span>
        </>}>
        {(close) => volume.map((d) => (
          <button key={d.id} type="button" role="menuitemradio" aria-checked={d.id === doc.id}
            onClick={() => { close(); if (d.id !== doc.id) onGo(d); }}>
            <span>{d.chapter_number != null ? `${d.chapter_number} · ` : ""}{shownTitle(d)}</span>
            <span className="muted" style={{ marginLeft: "auto", paddingLeft: "var(--space-3, 12px)" }}>{d.progress}%</span>
          </button>
        ))}
      </Menu>
      <button type="button" className="quiet" aria-label="Next chapter" disabled={!next}
        onClick={() => next && onGo(next)}>›</button>
    </span>
  );
}
