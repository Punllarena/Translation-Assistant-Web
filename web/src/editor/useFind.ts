import { useEffect, useMemo, useRef, useState } from "react";
import { findHits, firstFrom, NO_HITS, wrapStep } from "./find";
import type { Row } from "./rows";

export function useFind(rows: Row[], texts: Record<number, string>, active: number, activate: (i: number) => void, glossaryRuby = false) {
  const [find, setFind] = useState({ open: 0, needle: "", at: -1 });
  const hits = useMemo(
    () => findHits(rows.flatMap((r) => r.kind === "line"
      ? [{
          index: r.index,
          source: glossaryRuby ? r.line.plain_text : r.line.display_text,
          translation: texts[r.line.line_number] ?? "",
        }]
      : []), find.needle),
    [rows, texts, find.needle, glossaryRuby],
  );
  const at = find.at < hits.length ? find.at : -1;
  const hit = find.open && at >= 0 ? hits[at] : null;
  const stepped = useRef(false); // the next editor mount comes from a find step: leave focus in the bar
  useEffect(() => { stepped.current = false; }, [active]);
  const step = (dir: 1 | -1) => {
    const next = at < 0 && dir === 1 ? firstFrom(hits, active) : wrapStep(at, hits.length, dir);
    setFind((f) => ({ ...f, at: next }));
    if (hits[next] && hits[next].index !== active) {
      stepped.current = true;
      activate(hits[next].index);
    }
  };
  return {
    open: find.open, needle: find.needle, at, total: hits.length, hit,
    hits: find.open ? hits : NO_HITS, // every match, so each card can mark its own
    stepped, step,
    show: () => setFind((f) => ({ ...f, open: f.open + 1 })),
    close: () => { stepped.current = false; setFind((f) => ({ ...f, open: 0, at: -1 })); },
    setNeedle: (needle: string) => setFind((f) => ({ ...f, needle, at: -1 })),
  };
}
