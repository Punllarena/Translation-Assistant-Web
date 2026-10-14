import { useMutation } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router";
import { api, call } from "../api/client";

/** /invite?token=… — the link an admin hands out. Creates the account; the user then signs in. */
export default function AcceptInvite() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const accept = useMutation({
    mutationFn: () =>
      call(api.POST("/auth/accept-invite", { body: { token, email, password } })),
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    accept.mutate();
  };
  if (accept.isSuccess) {
    return (
      <main className="auth">
        <div className="auth-card">
          <span className="brand"><span className="mark" aria-hidden="true">訳</span>Translation Assistant</span>
          <h1>Account created</h1>
          <p><Link to="/login">Sign in</Link> with your email and password.</p>
        </div>
      </main>
    );
  }
  return (
    <main className="auth">
      <form className="auth-card" onSubmit={submit}>
        <span className="brand"><span className="mark" aria-hidden="true">訳</span>Translation Assistant</span>
        <h1>Create your account</h1>
        {!token && <p className="box danger">This link has no invite token.</p>}
        <label className="field"><span>Email</span>
          <input type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} /></label>
        <label className="field"><span>Password</span>
          <input type="password" autoComplete="new-password" required minLength={12} value={password}
            onChange={(e) => setPassword(e.target.value)} aria-describedby="pw-hint" /></label>
        <p id="pw-hint" className="hint">At least 12 characters.</p>
        <button className="primary" disabled={!token || accept.isPending}>Create account</button>
        {accept.isError && <p className="box danger" role="alert">{accept.error.message}</p>}
      </form>
    </main>
  );
}
