import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Navigate, useNavigate, useSearchParams } from "react-router";
import { api, call } from "../api/client";
import { safeNext } from "./next";
import { useMe } from "./session";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [params] = useSearchParams();
  const next = safeNext(params.get("next"));
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const me = useMe();
  const login = useMutation({
    mutationFn: () => call(api.POST("/auth/login", { body: { email, password } })),
    onSuccess: (user) => {
      queryClient.setQueryData(["me"], user);
      navigate(next, { replace: true });
    },
  });
  if (me.data) return <Navigate to={next} replace />;
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
