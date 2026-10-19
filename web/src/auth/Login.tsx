import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, Navigate, useSearchParams } from "react-router";
import { api, call } from "../api/client";
import { safeNext } from "./next";
import { forgetUserData, useMe, useSetupStatus } from "./session";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [params] = useSearchParams();
  const next = safeNext(params.get("next"));
  const [target, setTarget] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const me = useMe();
  const setup = useSetupStatus();
  const login = useMutation({
    mutationFn: () => call(api.POST("/auth/login", { body: { email, password } })),
    onSuccess: async (user) => {
      forgetUserData(queryClient);
      // Pick the destination before marking the user signed in: one navigation, so a link the
      // user clicks right after it is never overridden by a late redirect.
      let to = next;
      if (next === "/") {
        // Restore the last opened chapter (spec §6); a deleted one just answers 404 there.
        const settings = await call(api.GET("/settings")).catch(() => null);
        const last = Number(settings?.last_document_id);
        if (Number.isInteger(last) && last > 0) to = `/documents/${last}`;
      }
      setTarget(to);
      queryClient.setQueryData(["me"], user);
    },
  });
  if (me.data) return <Navigate to={target ?? next} replace />;
  const submit = (e: FormEvent) => {
    e.preventDefault();
    login.mutate();
  };
  return (
    <main className="auth">
      <form className="auth-card" onSubmit={submit}>
        <span className="brand"><span className="mark" aria-hidden="true">訳</span>Translation Assistant</span>
        <h1>Sign in</h1>
        {setup.data?.needed && (
          <p className="box warn" role="status">
            <span>This server has no accounts yet. Open the setup link printed in the server log
              (<code>docker compose logs api</code>), or go to <Link to="/setup">setup</Link> and paste its token.</span>
          </p>
        )}
        <label className="field"><span>Email</span>
          <input type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} /></label>
        <label className="field"><span>Password</span>
          <input type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} /></label>
        {login.isError && <p className="box danger" role="alert">{login.error.message}</p>}
        <button className="primary" disabled={login.isPending}>Sign in</button>
        <p className="hint">Accounts are by invitation. Ask the person who runs this server for a link.</p>
      </form>
    </main>
  );
}
