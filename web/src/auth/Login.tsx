import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Navigate, useSearchParams } from "react-router";
import { api, call } from "../api/client";
import { safeNext } from "./next";
import { forgetUserData, useMe } from "./session";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [params] = useSearchParams();
  const next = safeNext(params.get("next"));
  const [target, setTarget] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const me = useMe();
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
    <main>
      <h1>Sign in</h1>
      <form className="stack" onSubmit={submit}>
        <label>
          Email <input type="email" autoComplete="username" required value={email}
            onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label>
          Password <input type="password" autoComplete="current-password" required value={password}
            onChange={(e) => setPassword(e.target.value)} />
        </label>
        <button disabled={login.isPending}>Sign in</button>
        {login.isError && <p className="error" role="alert">{login.error.message}</p>}
      </form>
    </main>
  );
}
