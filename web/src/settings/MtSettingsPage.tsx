import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";
import { api, call, type Schemas } from "../api/client";

type Kind = "deepl" | "libretranslate" | "ollama";
const LABELS: Record<string, string> = {
  deepl: "DeepL", libretranslate: "LibreTranslate", ollama: "Ollama", mecab: "MeCab", jparser: "JParser",
};
const form = (e: FormEvent<HTMLFormElement>) => {
  e.preventDefault();
  return new FormData(e.currentTarget);
};

/** Machine translation: target language, panel order, backend credentials and Ollama options. */
export default function MtSettingsPage() {
  const queryClient = useQueryClient();
  const backends = useQuery({ queryKey: ["mt", "backends"], queryFn: () => call(api.GET("/mt/backends")) });
  const settings = useQuery({ queryKey: ["mt", "settings"], queryFn: () => call(api.GET("/settings")) });
  const creds = useQuery({ queryKey: ["mt", "credentials"], queryFn: () => call(api.GET("/credentials")) });
  const [note, setNote] = useState("");
  const [order, setOrder] = useState<string[] | null>(null); // local row order; null = from the server
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["mt"] });
  const done = (msg: string) => () => { setNote(msg); return refresh(); };

  const rows = backends.data?.backends ?? [];
  const enabled = backends.data?.enabled ?? [];
  const names: string[] = rows.map((b) => b.name);
  const shown = (order ?? [...enabled, ...names.filter((n) => !enabled.includes(n))]).filter((n) => names.includes(n));
  const [checked, setChecked] = useState<string[] | null>(null);
  const on = checked ?? enabled;
  const enabledKey = enabled.join(",");
  useEffect(() => { setOrder(null); setChecked(null); }, [enabledKey]);

  const putSetting = useMutation({
    mutationFn: (body: Record<string, unknown>) => call(api.PUT("/settings", { body })),
    onSuccess: done("Saved"),
    onError: () => { setOrder(null); setChecked(null); },
  });
  const resetPrompt = useMutation({
    mutationFn: () => call(api.DELETE("/settings/{key}", { params: { path: { key: "ollama_system_prompt" } } })),
    onSuccess: done("Prompt reset"),
  });
  const saveCred = useMutation({
    mutationFn: async (v: { kind: Kind; secret?: string; endpoint_url?: string }) => {
      const existing = creds.data?.find((c) => c.kind === v.kind && c.name === "");
      const { kind, ...rest } = v;
      if (!existing) return call(api.POST("/credentials", { body: { kind, name: "", secret: "", endpoint_url: "", ...rest } as Schemas["CredentialCreate"] }));
      return call(api.PATCH("/credentials/{credential_id}", { params: { path: { credential_id: existing.id } }, body: rest }));
    },
    onSuccess: done("Saved"),
  });

  const saveOrder = (next: string[], on2: string[]) => {
    setOrder(next);
    setChecked(on2);
    putSetting.mutate({ mt_enabled: next.filter((n) => on2.includes(n)) });
  };
  const move = (i: number, d: number) => {
    const next = [...shown];
    [next[i], next[i + d]] = [next[i + d], next[i]];
    saveOrder(next, on);
  };
  const toggle = (n: string) =>
    saveOrder(shown, on.includes(n) ? on.filter((x) => x !== n) : [...on, n]);

  const cred = (kind: Kind) => creds.data?.find((c) => c.kind === kind && c.name === "");
  const keyState = (kind: Kind) => {
    const c = cred(kind);
    return c?.secret_unreadable ? "Saved key cannot be read; enter it again" : c?.has_secret ? `Key saved ${c.secret_hint}` : "No key saved";
  };
  const s = settings.data ?? {};
  const error = [backends, settings, creds].map((q) => q.error?.message).find(Boolean)
    ?? putSetting.error?.message ?? resetPrompt.error?.message ?? saveCred.error?.message;
  const typed = (v: FormDataEntryValue | null) => String(v ?? "").trim();

  return (
    <main>
      <h1>Machine translation</h1>
      {error && <p className="error" role="alert">{error}</p>}
      {note && <p role="status">{note}</p>}
      {backends.data && (
        <>
          <label>Target language{" "}
            <select aria-label="Target language" value={backends.data.target}
              onChange={(e) => putSetting.mutate({ mt_target: e.target.value })}>
              {Object.entries(backends.data.languages).map(([code, name]) => <option key={code} value={code}>{name}</option>)}
            </select>
          </label>
          <h2>Panels</h2>
          <ul>
            {shown.map((n, i) => {
              const b = rows.find((r) => r.name === n)!;
              return (
                <li key={n} className="toolbar">
                  <label><input type="checkbox" aria-label={`Show ${LABELS[n]}`} checked={on.includes(n)} onChange={() => toggle(n)} /> {LABELS[n]}</label>
                  <button aria-label={`Move ${LABELS[n]} up`} disabled={i === 0} onClick={() => move(i, -1)}>↑</button>
                  <button aria-label={`Move ${LABELS[n]} down`} disabled={i === shown.length - 1} onClick={() => move(i, 1)}>↓</button>
                  <span className="muted" data-testid={`status-${n}`}>{b.available ? "Ready" : b.message}</span>
                </li>
              );
            })}
          </ul>
        </>
      )}
      <h2>DeepL</h2>
      <form className="toolbar" onSubmit={(e) => { const f = e.currentTarget; const secret = typed(form(e).get("k")); if (secret) saveCred.mutate({ kind: "deepl", secret }, { onSuccess: () => f.reset() }); }}>
        <input type="password" name="k" aria-label="DeepL API key" autoComplete="off" />
        <button type="submit">Save DeepL</button>
        <span className="muted">{keyState("deepl")}</span>
      </form>
      <h2>LibreTranslate</h2>
      <form key={cred("libretranslate")?.endpoint_url} className="toolbar" onSubmit={(e) => {
        const el = e.currentTarget; const f = form(e); const secret = typed(f.get("k"));
        saveCred.mutate({ kind: "libretranslate", endpoint_url: typed(f.get("u")), ...(secret ? { secret } : {}) },
          { onSuccess: () => { (el.elements.namedItem("k") as HTMLInputElement).value = ""; } });
      }}>
        <input name="u" aria-label="LibreTranslate URL" defaultValue={cred("libretranslate")?.endpoint_url ?? ""} />
        <input type="password" name="k" aria-label="LibreTranslate API key" autoComplete="off" />
        <button type="submit">Save LibreTranslate</button>
        <span className="muted">{keyState("libretranslate")}</span>
      </form>
      <h2>Ollama</h2>
      <form key={cred("ollama")?.endpoint_url} className="toolbar" onSubmit={(e) => saveCred.mutate({ kind: "ollama", endpoint_url: typed(form(e).get("u")) })}>
        <input name="u" aria-label="Ollama URL" placeholder="server default" defaultValue={cred("ollama")?.endpoint_url ?? ""} />
        <button type="submit">Save Ollama URL</button>
      </form>
      <form key={`${s.ollama_model}|${s.ollama_system_prompt}`} onSubmit={(e) => {
        const f = form(e);
        putSetting.mutate({ ollama_model: typed(f.get("m")), ollama_system_prompt: String(f.get("p") ?? "") });
      }}>
        <p><input name="m" aria-label="Ollama model" defaultValue={String(s.ollama_model ?? "")} /></p>
        <p><textarea name="p" aria-label="Ollama system prompt" rows={8} placeholder={backends.data?.ollama_default_prompt}
          defaultValue={String(s.ollama_system_prompt ?? "")} /></p>
        <button type="submit">Save Ollama options</button>{" "}
        <button type="button" onClick={() => resetPrompt.mutate()}>Reset</button>
      </form>
    </main>
  );
}
