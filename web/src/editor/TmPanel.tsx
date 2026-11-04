import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { api, call } from "../api/client";
import { useAidReady } from "./AidCount";
import { CardAction, CardReady, CardStatus } from "./CardParts";
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
  useAidReady("tm", aid === "ready");
  return (
    <aside className={`mt-card tm-panel state-${aid}`} aria-label="Translation memory">
      <header>
        <h3>Translation memory</h3>
        <span className="card-meta">
          {aid === "ready" && <CardReady />}
          {aid === "empty" && <span className="card-note muted">No match</span>}
        </span>
      </header>
      {tm.error && (
        <>
          <CardStatus kind="error">{friendlyError(tm.error.message, "translation memory", false)}</CardStatus>
          <div className="mt-actions"><CardAction onClick={() => void tm.refetch()}>Retry</CardAction></div>
        </>
      )}
      {aid === "busy" && <CardStatus kind="busy">{stale && matches.length ? "Searching this line" : "Searching"}</CardStatus>}
      {matches.length > 0 && (
        <ul>
          {matches.map((m, i) => {
            const slot = !stale && i < slots.tm.length ? slots.tm[i] : null;
            const key = slot !== null ? bindings[`use_${slot}`] : undefined;
            return (
              // The row is the click; only the Use button is a stop in the tab order.
              <li key={i} className="tm-match"
                onClick={(e) => { if (!stale && !(e.target as Element).closest("button")) onUse(m.translated_text); }}>
                <span className={stale ? "tm-text muted" : "tm-text"}>{m.translated_text}</span>
                <CardAction tone="use" slot={slot ?? undefined} keyLabel={key} disabled={stale}
                  label={key ? `Use "${m.translated_text}", ${key}` : `Use "${m.translated_text}"`}
                  onClick={() => onUse(m.translated_text)}>Use</CardAction>
                <span className="muted tm-source">{m.document_title}, {m.updated_at.slice(0, 10)}</span>
              </li>
            );
          })}
        </ul>
      )}
    </aside>
  );
}
