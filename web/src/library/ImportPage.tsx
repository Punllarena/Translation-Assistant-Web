import { Link } from "react-router";
import PageHeader from "../ui/PageHeader";
import ImportEpub from "./ImportEpub";
import ImportFiles from "./ImportFiles";
import ImportTadb from "./ImportTadb";
import { useSeriesList } from "./queries";

export default function ImportPage() {
  const series = useSeriesList();
  if (series.isPending) return <main><p className="muted">Loading…</p></main>;
  if (series.isError) return <main><p className="error">{series.error.message}</p></main>;
  return (
    <main className="settings">
      <PageHeader title="Import" crumbs={<><Link to="/">Library</Link><span aria-hidden="true">/</span><span>Import</span></>} />
      <div className="cols import-cols">
        <ImportFiles series={series.data} />
        <ImportEpub series={series.data} />
        <ImportTadb />
      </div>
    </main>
  );
}
