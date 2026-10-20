import { useQuery } from "@tanstack/react-query";
import { Link, useParams, useSearchParams } from "react-router";
import { api, call } from "../api/client";
import PageHeader from "../ui/PageHeader";
import { useDocuments, useSeriesList } from "./queries";
import SeriesSettings from "./SeriesSettings";
import SeriesTools from "./SeriesTools";
import VolumesTab from "./VolumesTab";

const TABS = [
  { id: "volumes", label: "Volumes" },
  { id: "tools", label: "Tools" },
  { id: "settings", label: "Settings" },
] as const;

export default function SeriesPage() {
  const seriesId = Number(useParams().id);
  const [params, setParams] = useSearchParams();
  const all = useSeriesList();
  const docs = useDocuments();
  const profiles = useQuery({ queryKey: ["profiles"], queryFn: () => call(api.GET("/profiles")) });
  if (all.isPending || docs.isPending) return <main><p className="muted">Loading…</p></main>;
  const loadError = all.error ?? docs.error;
  if (loadError) return <main><p className="error" role="alert">{loadError.message}</p></main>;
  const series = all.data?.find((s) => s.id === seriesId);
  if (!series) return <main><p>No such series. <Link to="/">Back to the library</Link></p></main>;
  const chapters = (docs.data ?? []).filter((d) => d.series_id === seriesId);
  const tab = TABS.find((t) => t.id === params.get("tab"))?.id ?? "volumes";
  const select = (id: string) => {
    const next = new URLSearchParams(params);
    next.set("tab", id);
    setParams(next, { replace: true });
  };
  return (
    <main>
      <PageHeader title={series.title}
        crumbs={<><Link to="/">Library</Link><span aria-hidden="true">/</span><span>{series.title}</span></>} />
      <div className="tabs" role="tablist" aria-label="Series sections">
        {TABS.map((t) => (
          <button key={t.id} type="button" role="tab" id={`tab-${t.id}`} aria-selected={tab === t.id}
            aria-controls={`panel-${t.id}`} onClick={() => select(t.id)}>{t.label}</button>
        ))}
      </div>
      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
        {tab === "volumes" && <VolumesTab series={series} docs={chapters} />}
        {tab === "tools" && (
          <SeriesTools series={series}
            defaultProfileId={series.profile_id ?? profiles.data?.find((p) => p.is_default)?.id ?? null} />
        )}
        {tab === "settings" && <SeriesSettings series={series} chapterCount={chapters.length} />}
      </div>
    </main>
  );
}
