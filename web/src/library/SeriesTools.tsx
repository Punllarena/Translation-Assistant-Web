import FindReplace from "./FindReplace";
import PhraseSuggestions from "./PhraseSuggestions";
import type { SeriesRow } from "./shelf";
import SyosetuFetch from "./SyosetuFetch";

export default function SeriesTools({ series, defaultProfileId }: { series: SeriesRow; defaultProfileId: number | null }) {
  return (
    <>
      {series.syosetu_url && <SyosetuFetch key={`fetch-${series.id}`} seriesId={series.id} />}
      <FindReplace key={`find-${series.id}`} seriesId={series.id} />
      <PhraseSuggestions key={`suggest-${series.id}`} seriesId={series.id} defaultProfileId={defaultProfileId} />
    </>
  );
}
