import { useLocation } from "react-router";
import FindReplace from "./FindReplace";
import PhraseSuggestions from "./PhraseSuggestions";
import type { SeriesRow } from "./shelf";
import SyosetuFetch from "./SyosetuFetch";

export default function SeriesTools({ series }: { series: SeriesRow }) {
  const fetchError = (useLocation().state as { fetchError?: string } | null)?.fetchError;
  return (
    <>
      {fetchError && <p className="error" role="alert">{fetchError} Use Fetch from Syosetu below to try again.</p>}
      {series.syosetu_url && <SyosetuFetch key={`fetch-${series.id}`} series={series} />}
      <FindReplace key={`find-${series.id}`} seriesId={series.id} />
      <PhraseSuggestions key={`suggest-${series.id}`} seriesId={series.id} />
    </>
  );
}
