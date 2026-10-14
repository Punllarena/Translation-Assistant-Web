import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { api, call, type Schemas } from "../api/client";
import PageHeader from "../ui/PageHeader";
import { KeyState } from "./MtSettingsPage";

/** Settings → WordPress: endpoint and API key (a credential), publish defaults (user settings), a connection test. */
export default function WpSettingsPage() {
  const queryClient = useQueryClient();
  const prefs = useQuery({ queryKey: ["wp", "prefs"], queryFn: () => call(api.GET("/wp/prefs")) });
  const creds = useQuery({ queryKey: ["wp", "credentials"], queryFn: () => call(api.GET("/credentials")) });
  const [note, setNote] = useState("");
  const cred = creds.data?.find((c) => c.kind === "wordpress" && c.name === "");
  const refresh = (msg: string) => { setNote(msg); return queryClient.invalidateQueries({ queryKey: ["wp"] }); };

  const saveCred = useMutation({
    mutationFn: (v: { endpoint_url: string; secret?: string }) => cred
      ? call(api.PATCH("/credentials/{credential_id}", { params: { path: { credential_id: cred.id } }, body: v }))
      : call(api.POST("/credentials", { body: { kind: "wordpress", name: "", secret: v.secret ?? "", endpoint_url: v.endpoint_url } })),
    onSuccess: () => refresh("Saved"),
  });
  const savePrefs = useMutation({
    mutationFn: (body: Schemas["WpPrefsOut"]) => call(api.PUT("/settings", { body })),
    onSuccess: () => refresh("Saved"),
  });
  const test = useMutation({ mutationFn: () => call(api.POST("/wp/test")) });

  const submitCred = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const secret = String(f.get("key") ?? "").trim();
    const el = e.currentTarget;
    saveCred.mutate({ endpoint_url: String(f.get("url") ?? "").trim(), ...(secret ? { secret } : {}) },
      { onSuccess: () => { (el.elements.namedItem("key") as HTMLInputElement).value = ""; } });
  };
  const submitPrefs = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    savePrefs.mutate({
      wp_password_enabled: f.get("pw") === "on",
      wp_unlock_after: Number(f.get("unlock")),
      wp_attribution_enabled: f.get("attr") === "on",
      wp_default_schedule_time: f.get("timed") === "on" ? String(f.get("time")) : "",
      wp_chapters_per_day: Number(f.get("perday")),
      wp_schedule_scope_global: f.get("global") === "on",
    });
  };
  const keyState = cred?.secret_unreadable ? "Saved key cannot be read; enter it again"
    : cred?.has_secret ? `Key saved ${cred.secret_hint}` : "No key saved";
  const error = prefs.error ?? creds.error ?? saveCred.error ?? savePrefs.error ?? test.error;
  const p = prefs.data;
  return (
    <main className="settings">
      <PageHeader title="WordPress" subtitle="Publishing goes through the TA Publisher plugin on your site."
        actions={note ? <span role="status" className="saved-note">{note}</span> : undefined} />
      {error && <p className="error" role="alert">{error.message}</p>}
      <div className="cols">
        {creds.data && ( // not before it loads: a late remount would wipe what the user typed
          <form className="panel sec" key={cred?.endpoint_url ?? ""} onSubmit={submitCred} aria-labelledby="wp-conn-h">
            <div className="sec-head">
              <h2 id="wp-conn-h">Connection</h2>
              <KeyState text={keyState} ok={Boolean(cred?.has_secret && !cred.secret_unreadable)} />
            </div>
            <label className="field"><span>Endpoint URL</span>
              <input name="url" className="mono" aria-label="WordPress endpoint URL" required
                placeholder="https://yoursite.com/wp-json/ta-publisher/v1/publish" defaultValue={cred?.endpoint_url ?? ""} /></label>
            <label className="field"><span>API key</span>
              <input name="key" type="password" aria-label="WordPress API key" autoComplete="off"
                required={!cred} aria-describedby="wp-key-hint" /></label>
            <p id="wp-key-hint" className="hint">WP Admin → Settings → TA Publisher</p>
            <div className="toolbar">
              <button type="submit" className="primary" disabled={saveCred.isPending}>Save connection</button>
              <button type="button" disabled={!cred || test.isPending} onClick={() => test.mutate()}>Test connection</button>
            </div>
            {test.data && <p role="status" className={test.data.ok ? "box ok" : "box danger"}>{test.data.message}</p>}
          </form>
        )}

        {p && (
          <form className="panel sec" key={JSON.stringify(p)} onSubmit={submitPrefs} aria-labelledby="wp-def-h">
            <h2 id="wp-def-h">Publishing defaults</h2>
            <fieldset className="grp">
              <legend className="label">Chapter passwords</legend>
              <label className="check"><input type="checkbox" name="pw" defaultChecked={p.wp_password_enabled} /><span>Enable password protection by default</span></label>
              <label className="inline-field"><span>Keep N chapters locked</span>
                <input type="number" name="unlock" className="num-input mono" min={1} max={99} defaultValue={p.wp_unlock_after} /></label>
              <label className="check"><input type="checkbox" name="attr" defaultChecked={p.wp_attribution_enabled} /><span>Add attribution footer to published chapters</span></label>
            </fieldset>
            <fieldset className="grp">
              <legend className="label">Schedule</legend>
              <label className="check"><input type="checkbox" name="timed" defaultChecked={!!p.wp_default_schedule_time} /><span>Set default schedule time</span></label>
              <label className="inline-field"><span>Time</span>
                <input type="time" name="time" className="mono" defaultValue={p.wp_default_schedule_time || "20:00"} /></label>
              <label className="inline-field"><span>Chapters per day</span>
                <input type="number" name="perday" className="num-input mono" min={1} max={99} defaultValue={p.wp_chapters_per_day} /></label>
              <label className="check"><input type="checkbox" name="global" defaultChecked={p.wp_schedule_scope_global} /><span>Count chapters/day across all series</span></label>
            </fieldset>
            <div><button type="submit" disabled={savePrefs.isPending}>Save defaults</button></div>
          </form>
        )}
      </div>
    </main>
  );
}
