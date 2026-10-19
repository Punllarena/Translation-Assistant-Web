import { useMutation } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router";
import { api, call } from "../api/client";
import { useSetupStatus } from "./session";

/** /setup?token=… — creates the first admin on a server with no accounts. The API logs the
 *  link at startup (`docker compose logs api`). */
export default function Setup() {
  const [params] = useSearchParams();
  const [token, setToken] = useState(params.get("token") ?? "");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const status = useSetupStatus();
  const setup = useMutation({
    mutationFn: () => call(api.POST("/setup", { body: { token, email, password } })),
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setup.mutate();
  };
  const brand = <span className="brand"><span className="mark" aria-hidden="true">訳</span>Translation Assistant</span>;
  if (setup.isSuccess || status.data?.needed === false) {
    return (
      <main className="auth">
        <div className="auth-card">
          {brand}
          <h1>{setup.isSuccess ? "Admin created" : "Already set up"}</h1>
          <p><Link to="/login">Sign in</Link>{setup.isSuccess ? " with your email and password." : "."}</p>
        </div>
      </main>
    );
  }
  return (
    <main className="auth">
      <form className="auth-card" onSubmit={submit}>
        {brand}
        <h1>Set up this server</h1>
        <p className="hint">Create the first account. It is an admin and can invite others.</p>
        {!params.get("token") && (
          <label className="field"><span>Setup token</span>
            <input required value={token} onChange={(e) => setToken(e.target.value)} aria-describedby="token-hint" /></label>
        )}
        {!params.get("token") && <p id="token-hint" className="hint">Printed in the server log: <code>docker compose logs api</code>.</p>}
        <label className="field"><span>Email</span>
          <input type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} /></label>
        <label className="field"><span>Password</span>
          <input type="password" autoComplete="new-password" required minLength={12} value={password}
            onChange={(e) => setPassword(e.target.value)} aria-describedby="pw-hint" /></label>
        <p id="pw-hint" className="hint">At least 12 characters.</p>
        <button className="primary" disabled={!token || setup.isPending}>Create admin</button>
        {setup.isError && <p className="box danger" role="alert">{setup.error.message}</p>}
      </form>
    </main>
  );
}
