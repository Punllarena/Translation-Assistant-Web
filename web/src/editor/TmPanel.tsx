import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { api, call } from "../api/client";

/** Translation memory (desktop _update_tm_panel): earlier translations of this exact
 *  source line elsewhere; clicking one uses it. */
export default function TmPanel({ documentId, lineNumber, onUse }: {
  documentId: number; lineNumber: number; onUse(text: string): void;
}) {
  const tm = useQuery({
    queryKey: ["tm", documentId, lineNumber],
    queryFn: () => call(api.GET("/tm/matches", { params: { query: { document_id: documentId, line_number: lineNumber } } })),
    staleTime: 60_000,
    placeholderData: keepPreviousData, // no flicker between lines
  });
  const matches = tm.data ?? [];
  return (
    <aside className="tm-panel" aria-label="Translation memory">
      <h2>Translation memory</h2>
      {matches.length === 0 && <p className="muted">{tm.isPending ? "Searching\u2026" : "No matches"}</p>}
      <ul>
        {matches.map((m, i) => (
          <li key={i}>
            <button onClick={() => onUse(m.translated_text)}>{m.translated_text}</button>
            <span className="muted">{m.document_title}, {m.updated_at.slice(0, 10)}</span>
          </li>
        ))}
      </ul>
    </aside>
  );
}
