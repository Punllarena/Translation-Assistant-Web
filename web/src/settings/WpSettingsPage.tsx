import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { api, call, type Schemas } from "../api/client";

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
    <main>
      <h1>WordPress</h1>
      {error && <p className="error" role="alert">{error.message}</p>}
      {note && <p role="status">{note}</p>}
      <form className="stack" key={cred?.endpoint_url ?? ""} onSubmit={submitCred}>
        <label>Endpoint URL <input name="url" aria-label="WordPress endpoint URL" required
          placeholder="https://yoursite.com/wp-json/ta-publisher/v1/publish" defaultValue={cred?.endpoint_url ?? ""} /></label>
        <label>API key <input name="key" type="password" aria-label="WordPress API key" autoComplete="off"
          required={!cred} placeholder="WP Admin → Settings → TA Publisher" /></label>
        <span className="muted">{keyState}</span>
        <div className="toolbar">
          <button type="submit" disabled={saveCred.isPending}>Save connection</button>
          <button type="button" disabled={!cred || test.isPending} onClick={() => test.mutate()}>Test connection</button>
        </div>
        {test.data && <p role="status" className={test.data.ok ? "" : "error"}>{test.data.message}</p>}
      </form>
      {p && (
        <form className="stack" key={JSON.stringify(p)} onSubmit={submitPrefs}>
          <h2>Defaults</h2>
          <label><input type="checkbox" name="pw" defaultChecked={p.wp_password_enabled} /> Enable password protection by default</label>
          <label>Keep N chapters locked <input type="number" name="unlock" min={1} max={99} defaultValue={p.wp_unlock_after} /></label>
          <label><input type="checkbox" name="attr" defaultChecked={p.wp_attribution_enabled} /> Add attribution footer to published chapters</label>
          <label><input type="checkbox" name="timed" defaultChecked={!!p.wp_default_schedule_time} /> Set default schedule time</label>
          <label>Time <input type="time" name="time" defaultValue={p.wp_default_schedule_time || "20:00"} /></label>
          <label>Chapters per day <input type="number" name="perday" min={1} max={99} defaultValue={p.wp_chapters_per_day} /></label>
          <label><input type="checkbox" name="global" defaultChecked={p.wp_schedule_scope_global} /> Count chapters/day across all series</label>
          <div className="toolbar"><button type="submit" disabled={savePrefs.isPending}>Save defaults</button></div>
        </form>
      )}
    </main>
  );
}
