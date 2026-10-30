import { Link, useParams, useSearchParams } from "react-router";
import { useWpConfigured } from "../publish/useWpConfigured";
import PageHeader from "../ui/PageHeader";
import { useArchive, useDocuments, useSeriesList } from "./queries";
import GalleryTab from "./gallery/GalleryTab";
import SeriesGlossary from "./SeriesGlossary";
import SeriesSettings from "./SeriesSettings";
import SeriesTools from "./SeriesTools";
import SeriesWp from "./SeriesWp";
import VolumesTab from "./VolumesTab";

const TABS = [
  { id: "volumes", label: "Volumes" },
  { id: "gallery", label: "Gallery" },
  { id: "glossary", label: "Glossary" },
  { id: "tools", label: "Tools" },
  { id: "settings", label: "Settings" },
  { id: "wordpress", label: "WordPress", wp: true },
] as const;

export default function SeriesPage() {
  const seriesId = Number(useParams().id);
  const [params, setParams] = useSearchParams();
  const all = useSeriesList();
  const { unarchive } = useArchive(seriesId);
  const docs = useDocuments();
  const wpConfigured = useWpConfigured() === true;
  if (all.isPending || docs.isPending) return <main><p className="muted">Loading…</p></main>;
  const loadError = all.error ?? docs.error;
  if (loadError) return <main><p className="error" role="alert">{loadError.message}</p></main>;
  const series = all.data?.find((s) => s.id === seriesId);
  if (!series) return <main><p>No such series. <Link to="/">Back to the library</Link></p></main>;
  const chapters = (docs.data ?? []).filter((d) => d.series_id === seriesId);
  // No WordPress tab without a WordPress credential (spec §2).
  const tabs = TABS.filter((t) => !("wp" in t) || wpConfigured);
  const tab = tabs.find((t) => t.id === params.get("tab"))?.id ?? "volumes";
  const select = (id: string) => {
    const next = new URLSearchParams(params);
    next.set("tab", id);
    setParams(next, { replace: true });
  };
  return (
    <main>
      <PageHeader title={series.title}
        crumbs={<><Link to="/">Library</Link><span aria-hidden="true">/</span><span>{series.title}</span></>} />
      {series.archived_at && (
        <p className="muted">
          Archived · <button type="button" disabled={unarchive.isPending} onClick={() => unarchive.mutate()}>Unarchive</button>
          {unarchive.error && <span className="error" role="alert"> {unarchive.error.message}</span>}
        </p>
      )}
      <div className="tabs" role="tablist" aria-label="Series sections">
        {tabs.map((t) => (
          <button key={t.id} type="button" role="tab" id={`tab-${t.id}`} aria-selected={tab === t.id}
            aria-controls={`panel-${t.id}`} onClick={() => select(t.id)}>{t.label}</button>
        ))}
      </div>
      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
        {tab === "volumes" && <VolumesTab series={series} docs={chapters} />}
        {tab === "gallery" && <GalleryTab series={series} docs={chapters} />}
        {tab === "glossary" && <SeriesGlossary key={series.id} seriesId={series.id} />}
        {tab === "tools" && <SeriesTools series={series} />}
        {tab === "settings" && <SeriesSettings key={`${series.id}:${series.volume_title_template}`} series={series} chapterCount={chapters.length} />}
        {tab === "wordpress" && wpConfigured && <SeriesWp key={series.id} series={series} />}
      </div>
    </main>
  );
}
