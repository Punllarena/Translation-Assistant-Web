import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { Link } from "react-router";
import { api, call } from "../api/client";

/** The whole page during maintenance: every other API call answers 503, this one does not. */
export default function RestorePage() {
  const queryClient = useQueryClient();
  const status = useQuery({
    queryKey: ["restore", "status"],
    queryFn: () => call(api.GET("/restore/status")),
    refetchInterval: (query) => (query.state.data?.phase === "restoring" ? 1000 : false),
  });
  const s = status.data;
  useEffect(() => {
    // Everything cached belongs to the replaced server; a stale library would be a lie.
    if (s?.phase === "done") queryClient.clear();
  }, [s?.phase, queryClient]);
  return (
    <main className="settings">
      <h1>Restore</h1>
      {status.isPending && <p className="muted">Checking…</p>}
      {status.isError && <p className="error" role="alert">{status.error.message}</p>}
      {s?.phase === "restoring" && (
        <section className="panel sec" aria-labelledby="restore-h">
          <div className="sec-head"><h2 id="restore-h">Restoring</h2></div>
          {s.total > 0
            ? <progress value={s.done} max={s.total} aria-label="Restore progress" />
            : <progress aria-label="Restore progress" />}
          <p className="muted">{s.total > 0 ? `${s.done} of ${s.total}` : "Starting…"}{s.message ? ` · ${s.message}` : ""}</p>
          <p className="hint">The server answers nothing else until this finishes. Do not close the server.</p>
        </section>
      )}
      {s?.phase === "done" && (
        <section className="panel sec" aria-labelledby="done-h">
          <div className="sec-head"><h2 id="done-h">Restore finished</h2></div>
          <p>Restore finished. Sign in with an account from the backup.</p>
          {s.error && <p className="box danger" role="alert">{s.error}</p>}
          <p><Link className="primary" to="/login">Sign in</Link></p>
        </section>
      )}
      {s?.phase === "failed" && (
        <section className="panel sec" aria-labelledby="failed-h">
          <div className="sec-head"><h2 id="failed-h">Restore failed</h2></div>
          {s.error && <p className="box danger" role="alert">{s.error}</p>}
          <p>The server was not changed.</p>
          <p><Link to="/">Back to the library</Link></p>
        </section>
      )}
      {s?.phase === "idle" && (
        <section className="panel sec" aria-labelledby="idle-h">
          <div className="sec-head"><h2 id="idle-h">No restore</h2></div>
          <p>No restore is running.</p>
          <p><Link to="/">Back to the library</Link></p>
        </section>
      )}
    </main>
  );
}
