import ImportEpub from "./ImportEpub";
import ImportFiles from "./ImportFiles";
import { useSeriesList } from "./queries";

export default function ImportPage() {
  const series = useSeriesList();
  if (series.isPending) return <main><p className="muted">Loading…</p></main>;
  if (series.isError) return <main><p className="error">{series.error.message}</p></main>;
  return (
    <main>
      <h1>Import</h1>
      <section>
        <h2>TXT and CSV files</h2>
        <ImportFiles series={series.data} />
      </section>
      <section>
        <h2>EPUB</h2>
        <ImportEpub series={series.data} />
      </section>
    </main>
  );
}
