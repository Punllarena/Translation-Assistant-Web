import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { api, call } from "../api/client";

/** Translation memory (desktop _update_tm_panel): earlier translations of this exact
 *  source line elsewhere; clicking one uses it. The first two weigh 1 and 2, whatever
 *  the machine translation cards do. */
export default function TmPanel({ documentId, lineNumber, onUse, slots, bindings }: {
  documentId: number; lineNumber: number; onUse(text: string): void;
  slots: { tm: readonly number[] }; bindings: Record<string, string>;
}) {
  const tm = useQuery({
    queryKey: ["tm", documentId, lineNumber],
    queryFn: () => call(api.GET("/tm/matches", { params: { query: { document_id: documentId, line_number: lineNumber } } })),
    staleTime: 60_000,
    placeholderData: keepPreviousData, // no flicker between lines
  });
  const matches = tm.data ?? [];
  // The matches still shown are the previous line's while this line's answer is on its way:
  // they can be read, but not used.
  const stale = tm.isPlaceholderData;
  return (
    <aside className="tm-panel" aria-label="Translation memory">
      <h2>Translation memory</h2>
      {matches.length === 0 && <p className="muted">{tm.isPending ? "Searching\u2026" : "No matches"}</p>}
      <ul>
        {matches.map((m, i) => {
          const slot = !stale && i < slots.tm.length ? slots.tm[i] : null;
          return (
            <li key={i}>
              <button data-use={slot ?? undefined} disabled={stale} className={stale ? "muted" : undefined}
                onClick={() => onUse(m.translated_text)}>
                {slot !== null && <span className="use-key" aria-hidden="true">{bindings[`use_${slot}`]}</span>}
                {m.translated_text}
              </button>
              <span className="muted">{m.document_title}, {m.updated_at.slice(0, 10)}</span>
            </li>
          );
        })}
      </ul>
    </aside>
  );
}
