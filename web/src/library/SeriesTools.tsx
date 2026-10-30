import { useState } from "react";
import { useLocation } from "react-router";
import { ConfirmDialog } from "../ui/Dialog";
import FindReplace from "./FindReplace";
import PhraseSuggestions from "./PhraseSuggestions";
import type { SeriesRow } from "./shelf";
import SyosetuFetch from "./SyosetuFetch";
import { useFlushOllama, useQueueOllama } from "./useOllamaQueue";

/** The series-wide Ollama actions (spec §1): the selection bar no longer carries them. */
function OllamaTools({ series }: { series: SeriesRow }) {
  const queue = useQueueOllama();
  const [flushing, setFlushing] = useState(false);
  const flush = useFlushOllama(() => setFlushing(false));
  return (
    <section>
      <h2>Ollama</h2>
      <div className="toolbar">
        <button type="button" disabled={queue.pending}
          onClick={() => queue.queue({ kind: "series", series_id: series.id })}>Queue series for Ollama</button>
        <button type="button" onClick={() => { flush.reset(); setFlushing(true); }}>Flush Ollama output…</button>
      </div>
      {queue.note && <p className="muted" role="status">{queue.note}</p>}
      {queue.error && <p className="error" role="alert">{queue.error}</p>}
      {flushing && (
        <ConfirmDialog title="Flush Ollama output" confirmLabel="Flush" danger busy={flush.pending}
          message="Clear Ollama's saved suggestions for every chapter of this series? Your own translation is not touched."
          error={flush.error} onConfirm={() => flush.flush({ series_id: series.id })} onClose={() => setFlushing(false)} />
      )}
    </section>
  );
}

export default function SeriesTools({ series }: { series: SeriesRow }) {
  const fetchError = (useLocation().state as { fetchError?: string } | null)?.fetchError;
  return (
    <>
      {fetchError && <p className="error" role="alert">{fetchError} Use Fetch from Syosetu below to try again.</p>}
      {series.syosetu_url && <SyosetuFetch key={`fetch-${series.id}`} series={series} />}
      <OllamaTools key={`ollama-${series.id}`} series={series} />
      <FindReplace key={`find-${series.id}`} seriesId={series.id} />
      <PhraseSuggestions key={`suggest-${series.id}`} seriesId={series.id} />
    </>
  );
}
