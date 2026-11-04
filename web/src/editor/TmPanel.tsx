import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { api, call } from "../api/client";
import { CardAction, CardStatus } from "./CardParts";
import { friendlyError } from "./cardCopy";

/** Translation memory (desktop _update_tm_panel): earlier translations of this exact
 *  source line elsewhere; clicking one uses it. The first two weigh 1 and 2, whatever
 *  the machine translation cards do. It wears the same shell as the MT cards. */
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
  const aid = tm.error ? "error" : tm.isPending || stale ? "busy" : matches.length ? "ready" : "empty";
  return (
    <aside className={`mt-card tm-panel state-${aid}`} aria-label="Translation memory">
      <header>
        <h3>Translation memory</h3>
        {aid === "empty" && <span className="card-note muted">No match</span>}
      </header>
      {tm.error && (
        <>
          <CardStatus kind="error">{friendlyError(tm.error.message, "translation memory")}</CardStatus>
          <div className="mt-actions"><CardAction onClick={() => void tm.refetch()}>Retry</CardAction></div>
        </>
      )}
      {aid === "busy" && <CardStatus kind="busy">{stale && matches.length ? "Searching this line" : "Searching"}</CardStatus>}
      {matches.length > 0 && (
        <ul>
          {matches.map((m, i) => {
            const slot = !stale && i < slots.tm.length ? slots.tm[i] : null;
            return (
              <li key={i} className="tm-match">
                <button data-use={slot ?? undefined} disabled={stale} className={stale ? "muted" : undefined}
                  aria-label={slot !== null ? `Use "${m.translated_text}", ${bindings[`use_${slot}`]}` : `Use "${m.translated_text}"`}
                  onClick={() => onUse(m.translated_text)}>
                  <span className="tm-text">{m.translated_text}</span>
                  <span className={`tm-use card-action${stale ? "" : " card-use"}`} aria-hidden="true">
                    {slot !== null && <span className="use-key">{bindings[`use_${slot}`]}</span>}Use
                  </span>
                </button>
                <span className="muted tm-source">{m.document_title}, {m.updated_at.slice(0, 10)}</span>
              </li>
            );
          })}
        </ul>
      )}
    </aside>
  );
}
