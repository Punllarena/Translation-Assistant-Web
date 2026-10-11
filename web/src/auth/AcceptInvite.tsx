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
      <main>
        <p>Account created. <Link to="/login">Sign in</Link>.</p>
      </main>
    );
  }
  return (
    <main>
      <h1>Create your account</h1>
      {!token && <p className="error">This link has no invite token.</p>}
      <form className="stack" onSubmit={submit}>
        <label>
          Email <input type="email" autoComplete="username" required value={email}
            onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label>
          Password <input type="password" autoComplete="new-password" required minLength={12} value={password}
            onChange={(e) => setPassword(e.target.value)} />
        </label>
        <button disabled={!token || accept.isPending}>Create account</button>
        {accept.isError && <p className="error" role="alert">{accept.error.message}</p>}
      </form>
    </main>
  );
}
