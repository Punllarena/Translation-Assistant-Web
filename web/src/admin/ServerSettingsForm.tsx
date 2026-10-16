import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { api, call, type Schemas } from "../api/client";

type Entry = Schemas["ServerSettingOut"];
const FIELDS = [
  { key: "ollama_url", label: "Ollama URL", kind: "url", hint: "e.g. http://192.168.1.20:11434" },
  { key: "libretranslate_url", label: "LibreTranslate URL", kind: "url", hint: "Leave empty if you do not run one." },
  { key: "mt_allow_private_urls", label: "Allow private addresses for machine translation", kind: "bool",
    hint: "Ollama or LibreTranslate on this machine or your network? Turn this on." },
  { key: "wp_allow_private_urls", label: "Allow private addresses for WordPress", kind: "bool",
    hint: "Only if your WordPress runs on your own network." },
  { key: "syosetu_delay_seconds", label: "Seconds between syosetu requests", kind: "number", hint: "1 to 60." },
] as const;
const BADGE: Record<Entry["source"], string> = { db: "", env: "from env", default: "default" };

function read(f: FormData, kind: string, key: string): unknown {
  if (kind === "bool") return f.get(key) === "on";
  if (kind === "number") return Number(f.get(key));
  return String(f.get(key) ?? "").trim();
}

export default function ServerSettingsForm({ onSaved }: { onSaved?: () => void }) {
  const queryClient = useQueryClient();
  const [note, setNote] = useState("");
  const q = useQuery({ queryKey: ["admin", "settings"], queryFn: () => call(api.GET("/admin/settings")) });
  const refresh = (msg: string) => { setNote(msg); return queryClient.invalidateQueries({ queryKey: ["admin", "settings"] }); };
  const save = useMutation({
    mutationFn: async (changed: [string, unknown][]) => {
      for (const [key, value] of changed) await call(api.PUT("/admin/settings/{key}", { params: { path: { key } }, body: { value } }));
    },
    onSuccess: () => { void refresh("Saved"); onSaved?.(); },
  });
  const reset = useMutation({
    mutationFn: (key: string) => call(api.DELETE("/admin/settings/{key}", { params: { path: { key } } })),
    onSuccess: () => refresh("Reset"),
  });
  if (q.isPending) return <p className="muted">Loading…</p>;
  if (q.isError) return <p className="error">{q.error.message}</p>;
  const byKey = Object.fromEntries(q.data.map((e) => [e.key, e]));
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    // Only changed values: saving an untouched field would pin it and hide later env changes.
    const changed = FIELDS.map((d) => [d.key, read(f, d.kind, d.key)] as [string, unknown])
      .filter(([key, value]) => value !== byKey[key].value);
    if (changed.length) save.mutate(changed);
    else onSaved?.();
  };
  const error = save.error ?? reset.error;
  return (
    <form key={JSON.stringify(q.data)} onSubmit={submit} aria-label="Server settings">
      {FIELDS.map((d) => {
        const e = byKey[d.key];
        const badge = BADGE[e.source];
        return (
          <div key={d.key} className="field">
            {d.kind === "bool" ? (
              <label><input type="checkbox" name={d.key} defaultChecked={Boolean(e.value)} /> {d.label}</label>
            ) : (
              <label><span>{d.label}</span>
                <input name={d.key} className={d.kind === "url" ? "mono" : undefined}
                  {...(d.kind === "number" ? { type: "number", min: 1, max: 60, step: "any" } : { type: "text" })}
                  defaultValue={String(e.value)} /></label>
            )}
            <p className="hint">{d.hint}{badge && <> · <span className="muted">{badge}</span></>}
              {e.source === "db" && <> · <button type="button" onClick={() => reset.mutate(d.key)} aria-label={`Reset ${d.label}`}>Reset</button></>}</p>
          </div>
        );
      })}
      {error && <p className="error" role="alert">{error.message}</p>}
      <div className="toolbar">
        <button type="submit" className="primary" disabled={save.isPending}>Save</button>
        {note && <span role="status" className="saved-note">{note}</span>}
      </div>
    </form>
  );
}
