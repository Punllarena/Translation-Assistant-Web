import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, call } from "../api/client";
import RestoreForm from "../restore/RestoreForm";
import { backupProblem } from "./backupForm";

export default function BackupPanel() {
  // Polled, so the panel knows a restore started elsewhere (or in another tab).
  const status = useQuery({
    queryKey: ["restore", "status"],
    queryFn: () => call(api.GET("/restore/status")),
    refetchInterval: 5000,
  });
  const [pass, setPass] = useState("");
  const [repeat, setRepeat] = useState("");
  const problem = backupProblem(pass, repeat, status.data?.phase === "restoring");
  return (
    <section className="panel sec" aria-labelledby="backup-h">
      <div className="sec-head"><h2 id="backup-h">Backup &amp; restore</h2></div>
      <h3>Backup</h3>
      <form method="post" action="/api/admin/backup" aria-label="Download a backup">
        <label className="field"><span>Passphrase</span>
          <input name="passphrase" type="password" required minLength={12} autoComplete="new-password"
            value={pass} onChange={(e) => setPass(e.target.value)} /></label>
        <label className="field"><span>Repeat passphrase</span>
          <input type="password" required minLength={12} autoComplete="new-password"
            value={repeat} onChange={(e) => setRepeat(e.target.value)} /></label>
        <p className="hint">You need this passphrase to restore the saved passwords and keys from this file. It is not stored anywhere.</p>
        {problem && <p className="error" role="alert">{problem}</p>}
        <div className="toolbar">
          <button type="submit" className="primary" disabled={problem !== null}>Download backup</button>
        </div>
      </form>
      <h3>Restore</h3>
      <p className="hint">Restoring replaces everything on this server: accounts, libraries, settings and saved credentials. Everyone signs in again.</p>
      <RestoreForm endpoint="/api/admin/restore" confirmWord="RESTORE" />
    </section>
  );
}
