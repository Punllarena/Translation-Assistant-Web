import { useEffect, useRef, useState } from "react";
import type { Doc, Volume } from "../library/shelf";
import { pickGroups, toggleAll } from "./chapterPick";

function GroupBox({ label, ids, picked, onChange }: { label: string; ids: number[]; picked: Set<number>; onChange: () => void }) {
  const ref = useRef<HTMLInputElement>(null);
  const count = ids.filter((id) => picked.has(id)).length;
  useEffect(() => { if (ref.current) ref.current.indeterminate = count > 0 && count < ids.length; }, [count, ids.length]);
  return <input ref={ref} type="checkbox" aria-label={`All of ${label}`} checked={count > 0 && count === ids.length} onChange={onChange} />;
}

/** Chapters grouped by volume in reading order, with how many lines each has left to translate. */
export default function ChapterPicker({ seriesId, docs, volumes, syosetu, picked, onChange }: {
  seriesId: number; docs: Doc[]; volumes: Volume[]; syosetu: boolean;
  picked: Set<number>; onChange: (next: Set<number>) => void;
}) {
  const [filter, setFilter] = useState("");
  const groups = pickGroups(seriesId, docs, volumes, syosetu, filter);
  const rows = groups.flatMap((g) => g.rows);
  const untranslated = rows.filter((r) => r.left > 0).map((r) => r.doc.id);
  const toggle = (id: number) => onChange(toggleAll(picked, [id]));
  return (
    <fieldset className="queue-chapters">
      <legend className="label">Chapters</legend>
      <div className="queue-chapters-bar">
        <input type="search" placeholder="Filter by title" aria-label="Filter chapters by title" value={filter} onChange={(e) => setFilter(e.target.value)} />
        <button type="button" className="quiet" disabled={!untranslated.length} onClick={() => onChange(new Set([...picked, ...untranslated]))}>Tick untranslated</button>
        <button type="button" className="quiet" disabled={!picked.size} onClick={() => onChange(new Set())}>Clear</button>
      </div>
      <div className="queue-chapters-list">
        {groups.map((g) => {
          const ids = g.rows.map((r) => r.doc.id);
          return (
            <section key={g.key} aria-label={g.label}>
              {groups.length > 1 || g.key !== "none" ? (
                <label className="queue-chapters-group">
                  <GroupBox label={g.label} ids={ids} picked={picked} onChange={() => onChange(toggleAll(picked, ids))} />
                  <span>{g.label}</span>
                  <span className="hint">{ids.length} {ids.length === 1 ? "chapter" : "chapters"}</span>
                </label>
              ) : null}
              {g.rows.map((r) => (
                <label key={r.doc.id} className={r.left ? "queue-chapter" : "queue-chapter done"}>
                  <input type="checkbox" checked={picked.has(r.doc.id)} onChange={() => toggle(r.doc.id)} />
                  <span className="num">{r.number ?? ""}</span>
                  <span className="title">{r.doc.title}</span>
                  <span className="hint">{r.left ? `${r.left.toLocaleString()} to translate` : "translated"}</span>
                </label>
              ))}
            </section>
          );
        })}
        {!rows.length && <p className="hint">{filter ? "No chapter title matches." : "This series has no chapters."}</p>}
      </div>
      <p className="hint" aria-live="polite">{picked.size ? `${picked.size} ${picked.size === 1 ? "chapter" : "chapters"} ticked` : "Tick the chapters to queue."}</p>
    </fieldset>
  );
}
