import { useSearchParams } from "react-router";
import PageHeader from "../ui/PageHeader";
import { JobHistory, RunningList } from "./JobHistory";
import OllamaQueue from "./OllamaQueue";
import ScheduledTab from "./ScheduledTab";

const TABS = [
  { id: "running", label: "Running" },
  { id: "ollama", label: "Ollama queue" },
  { id: "scheduled", label: "Scheduled" },
  { id: "history", label: "History" },
] as const;

/** Every job in one place: /jobs?tab=running|ollama|scheduled|history. */
export default function JobsPage() {
  const [params, setParams] = useSearchParams();
  const tab = TABS.find((t) => t.id === params.get("tab"))?.id ?? "running";
  const select = (id: string) => {
    const next = new URLSearchParams(params);
    next.set("tab", id);
    setParams(next, { replace: true });
  };
  return (
    <main className="jobs-page">
      <PageHeader title="Jobs" />
      <div className="tabs" role="tablist" aria-label="Job sections">
        {TABS.map((t) => (
          <button key={t.id} type="button" role="tab" id={`tab-${t.id}`} aria-selected={tab === t.id}
            aria-controls={`panel-${t.id}`} onClick={() => select(t.id)}>{t.label}</button>
        ))}
      </div>
      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
        {tab === "running" && <RunningList />}
        {tab === "ollama" && <OllamaQueue />}
        {tab === "scheduled" && <ScheduledTab />}
        {tab === "history" && <JobHistory />}
      </div>
    </main>
  );
}
