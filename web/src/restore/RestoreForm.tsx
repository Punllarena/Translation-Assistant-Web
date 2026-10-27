import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router";
import { errorMessage } from "../api/client";

/** The restore file and its passphrase. On 202 the progress page takes over; on 4xx the
 *  server's plain message shows here and nothing was changed. */
export default function RestoreForm({ endpoint, confirmWord }: { endpoint: string; confirmWord?: string }) {
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const body = new FormData();
    const file = form.get("file");
    if (file instanceof File) body.set("file", file);
    body.set("passphrase", String(form.get("passphrase") ?? ""));
    if (confirmWord) body.set("confirm", String(form.get("confirm") ?? ""));
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(endpoint, { method: "POST", body, credentials: "same-origin" });
      if (response.status === 202) {
        navigate("/restore");
        return;
      }
      const payload: unknown = await response.json().catch(() => null);
      setError(errorMessage(payload ?? { detail: "The restore did not start." }));
    } catch {
      setError("The restore did not start.");
    } finally {
      setBusy(false);
    }
  };
  return (
    <form onSubmit={submit} aria-label="Restore from a backup">
      <label className="field"><span>Backup file</span><input name="file" type="file" accept=".zip,application/zip" required /></label>
      <label className="field"><span>Passphrase</span><input name="passphrase" type="password" required autoComplete="off" /></label>
      {confirmWord && (
        <label className="field"><span>Type {confirmWord} to confirm</span>
          <input name="confirm" required autoComplete="off" spellCheck={false} /></label>
      )}
      {error && <p className="error" role="alert">{error}</p>}
      <div className="toolbar"><button type="submit" className="primary" disabled={busy}>{busy ? "Restoring…" : "Restore"}</button></div>
    </form>
  );
}
