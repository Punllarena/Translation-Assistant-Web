import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";
import { api, call, type Schemas } from "../api/client";
import { ArrowDown, ArrowUp } from "../ui/icons";
import PageHeader from "../ui/PageHeader";

type Kind = "deepl" | "libretranslate" | "ollama";
const LABELS: Record<string, string> = {
  deepl: "DeepL", libretranslate: "LibreTranslate", ollama: "Ollama", mecab: "MeCab", jparser: "JParser",
};
const form = (e: FormEvent<HTMLFormElement>) => {
  e.preventDefault();
  return new FormData(e.currentTarget);
};

/** "Key saved …hint" with a green dot, or the reason there is none. */
export function KeyState({ text, ok }: { text: string; ok: boolean }) {
  return <span className="key-state"><span className={ok ? "dot ok" : "dot"} aria-hidden="true" />{text}</span>;
}

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
  const hasKey = (kind: Kind) => Boolean(cred(kind)?.has_secret && !cred(kind)?.secret_unreadable);
  const s = settings.data ?? {};
  const error = [backends, settings, creds].map((q) => q.error?.message).find(Boolean)
    ?? putSetting.error?.message ?? resetPrompt.error?.message ?? saveCred.error?.message;
  const typed = (v: FormDataEntryValue | null) => String(v ?? "").trim();

  return (
    <main className="settings">
      <PageHeader title="Machine translation"
        subtitle="Which panels appear beside the editor, in what order, and how each service is reached."
        actions={note ? <span role="status" className="saved-note">{note}</span> : undefined} />
      {error && <p className="error" role="alert">{error}</p>}
      <div className="cols">
        {backends.data && (
          <section className="panel sec mt-order" aria-labelledby="mt-panels-h">
            <h2 id="mt-panels-h">Panels</h2>
            <label className="field"><span>Target language</span>
              <select aria-label="Target language" value={backends.data.target}
                onChange={(e) => putSetting.mutate({ mt_target: e.target.value })}>
                {Object.entries(backends.data.languages).map(([code, name]) => <option key={code} value={code}>{name}</option>)}
              </select>
            </label>
            <p className="hint">Checked panels show in the editor in this order. Changes save as you make them.</p>
            <ul className="order-list">
              {shown.map((n, i) => {
                const b = rows.find((r) => r.name === n)!;
                return (
                  <li key={n}>
                    <label className="check"><input type="checkbox" aria-label={`Show ${LABELS[n]}`} checked={on.includes(n)} onChange={() => toggle(n)} />{LABELS[n]}</label>
                    <span className={b.available ? "badge ok" : "badge warn"} data-testid={`status-${n}`}>{b.available ? "Ready" : b.message}</span>
                    <button type="button" className="icon" aria-label={`Move ${LABELS[n]} up`} disabled={i === 0} onClick={() => move(i, -1)}><ArrowUp /></button>
                    <button type="button" className="icon" aria-label={`Move ${LABELS[n]} down`} disabled={i === shown.length - 1} onClick={() => move(i, 1)}><ArrowDown /></button>
                  </li>
                );
              })}
            </ul>
          </section>
        )}

        <div className="stack-col">
          <form className="panel sec" aria-labelledby="deepl-h" onSubmit={(e) => { const f = e.currentTarget; const secret = typed(form(e).get("k")); if (secret) saveCred.mutate({ kind: "deepl", secret }, { onSuccess: () => f.reset() }); }}>
            <div className="sec-head"><h2 id="deepl-h">DeepL</h2><KeyState text={keyState("deepl")} ok={hasKey("deepl")} /></div>
            <div className="inline-form">
              <label className="field grow"><span>API key</span>
                <input type="password" name="k" aria-label="DeepL API key" autoComplete="off"
                  placeholder={hasKey("deepl") ? "Enter a new key to replace the saved one" : undefined} /></label>
              <button type="submit">Save DeepL</button>
            </div>
          </form>

          {creds.data && ( // keyed forms render once saved values load, so a late remount can't wipe typing
            <form key={cred("libretranslate")?.endpoint_url} className="panel sec" aria-labelledby="lt-h" onSubmit={(e) => {
              const el = e.currentTarget; const f = form(e); const secret = typed(f.get("k"));
              saveCred.mutate({ kind: "libretranslate", endpoint_url: typed(f.get("u")), ...(secret ? { secret } : {}) },
                { onSuccess: () => { (el.elements.namedItem("k") as HTMLInputElement).value = ""; } });
            }}>
              <div className="sec-head"><h2 id="lt-h">LibreTranslate</h2><KeyState text={keyState("libretranslate")} ok={hasKey("libretranslate")} /></div>
              <div className="row-fields">
                <label className="field"><span>Server URL</span><input name="u" className="mono" aria-label="LibreTranslate URL" defaultValue={cred("libretranslate")?.endpoint_url ?? ""} /></label>
                <label className="field"><span>API key (optional)</span><input type="password" name="k" aria-label="LibreTranslate API key" autoComplete="off" /></label>
              </div>
              <div><button type="submit">Save LibreTranslate</button></div>
            </form>
          )}

          <section className="panel sec" aria-labelledby="ollama-h">
            <div className="sec-head">
              <h2 id="ollama-h">Ollama</h2>
              <KeyState text={keyState("ollama").replace("key", "token").replace("Key", "Token")} ok={hasKey("ollama")} />
            </div>
            {creds.data && (
              <form key={cred("ollama")?.endpoint_url} className="stack" onSubmit={(e) => {
                const el = e.currentTarget; const f = form(e); const secret = typed(f.get("k"));
                saveCred.mutate({ kind: "ollama", endpoint_url: typed(f.get("u")), ...(secret ? { secret } : {}) },
                  { onSuccess: () => { (el.elements.namedItem("k") as HTMLInputElement).value = ""; } });
              }}>
                <div className="row-fields">
                  <label className="field"><span>Server URL</span><input name="u" className="mono" aria-label="Ollama URL" placeholder="server default" defaultValue={cred("ollama")?.endpoint_url ?? ""} /></label>
                  <label className="field"><span>Token (optional)</span><input type="password" name="k" aria-label="Ollama token" autoComplete="off" /></label>
                </div>
                <div><button type="submit">Save Ollama URL</button></div>
              </form>
            )}
            {settings.data && (
              <form key={`${s.ollama_model}|${s.ollama_system_prompt}`} className="stack" onSubmit={(e) => {
                const f = form(e);
                putSetting.mutate({ ollama_model: typed(f.get("m")), ollama_system_prompt: String(f.get("p") ?? "") });
              }}>
                <label className="field"><span>Model</span><input name="m" className="mono" aria-label="Ollama model" defaultValue={String(s.ollama_model ?? "")} /></label>
                <label className="field"><span>System prompt</span>
                  <textarea name="p" aria-label="Ollama system prompt" rows={8} placeholder={backends.data?.ollama_default_prompt}
                    defaultValue={String(s.ollama_system_prompt ?? "")} aria-describedby="prompt-hint" /></label>
                <p id="prompt-hint" className="hint">Leave empty to use the built-in prompt. Reset clears your own.</p>
                <div className="toolbar">
                  <button type="submit">Save Ollama options</button>
                  <button type="button" className="quiet" onClick={() => resetPrompt.mutate()}>Reset</button>
                </div>
              </form>
            )}
          </section>
        </div>
      </div>
    </main>
  );
}
