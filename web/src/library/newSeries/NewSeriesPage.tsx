import { Link, useSearchParams } from "react-router";
import PageHeader from "../../ui/PageHeader";
import NewFromEpub from "./NewFromEpub";
import NewFromPaste from "./NewFromPaste";
import NewFromSyosetu from "./NewFromSyosetu";

const SOURCES = [
  { id: "syosetu", name: "Syosetu", text: "Start from a syosetu URL and fetch the first chapter." },
  { id: "epub", name: "EPUB", text: "Start from an EPUB of a volume you have." },
  { id: "paste", name: "Paste", text: "Start empty and paste chapters in yourself." },
] as const;

export default function NewSeriesPage() {
  const [params, setParams] = useSearchParams();
  const source = params.get("source");
  return (
    <main className="settings">
      <PageHeader title="New series" crumbs={<><Link to="/">Library</Link><span aria-hidden="true">/</span><span>New series</span></>} />
      {source === "syosetu" || source === "epub" || source === "paste" ? (
        <>
          <p><Link to="/new">Back</Link></p>
          {source === "syosetu" && <NewFromSyosetu />}
          {source === "epub" && <NewFromEpub />}
          {source === "paste" && <NewFromPaste />}
        </>
      ) : (
        <div className="cols">
          {SOURCES.map((s) => (
            <button key={s.id} type="button" className="panel pad source-card" onClick={() => setParams({ source: s.id })}>
              <strong>{s.name}</strong>
              <span className="muted">{s.text}</span>
            </button>
          ))}
        </div>
      )}
    </main>
  );
}
