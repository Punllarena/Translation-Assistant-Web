import { useSearchParams } from "react-router";
import OllamaStats from "./OllamaStats";
import TranslationStats from "./TranslationStats";

const TABS = [{ id: "translation", label: "Translation" }, { id: "ollama", label: "Ollama" }] as const;

/** Statistics: /stats?tab=translation|ollama (translation by default). */
export default function StatsPage() {
  const [params, setParams] = useSearchParams();
  const tab = TABS.find((t) => t.id === params.get("tab"))?.id ?? "translation";
  const select = (id: string) => {
    const next = new URLSearchParams(params);
    next.set("tab", id);
    setParams(next, { replace: true });
  };
  const tabs = (
    <div className="tabs" role="tablist" aria-label="Statistics sections">
      {TABS.map((t) => (
        <button key={t.id} type="button" role="tab" id={`tab-${t.id}`} aria-selected={tab === t.id}
          onClick={() => select(t.id)}>{t.label}</button>
      ))}
    </div>
  );
  return tab === "ollama" ? <OllamaStats tabs={tabs} /> : <TranslationStats tabs={tabs} />;
}
