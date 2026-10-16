import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent, type ReactNode } from "react";
import { Link, Navigate } from "react-router";
import { api, ApiError, call } from "../api/client";
import { useMe, useSetupStatus } from "../auth/session";

const STEPS = ["Create admin", "Server settings", "Dictionary", "Desktop library", "Done"] as const;

export default function SetupPage() {
  const setup = useSetupStatus();
  const me = useMe();
  // Decided once, on arrival: after step 1 needs_setup turns false, and the wizard must keep going.
  const [arrivedNeedingSetup] = useState(() => setup.data?.needs_setup ?? false);
  const [step, setStep] = useState(0);
  if (!arrivedNeedingSetup) return <Navigate to={me.data ? "/" : "/login"} replace />;
  const next = () => setStep((s) => s + 1);
  return (
    <main className="settings">
      <h1>Set up Translation Assistant</h1>
      <ol className="muted" aria-label="Setup steps">
        {STEPS.map((s, i) => <li key={s} aria-current={i === step ? "step" : undefined}>{s}</li>)}
      </ol>
      {step === 0 && <CreateAdmin onDone={next} />}
      {step === 1 && <Step title="Server settings" onNext={next}>{null}</Step>}
      {step === 2 && <Step title="Dictionary" onNext={next}>{null}</Step>}
      {step === 3 && <Step title="Desktop library" onNext={next}>{null}</Step>}
      {step === 4 && (
        <section className="panel sec" aria-labelledby="done-h">
          <h2 id="done-h">Done</h2>
          <p>Everything here can be changed later under Admin and Import.</p>
          <Link className="primary" to="/">Open the library</Link>
        </section>
      )}
    </main>
  );
}

export function Step({ title, onNext, children }: { title: string; onNext: () => void; children: ReactNode }) {
  return (
    <section className="panel sec" aria-labelledby="step-h">
      <div className="sec-head"><h2 id="step-h">{title}</h2></div>
      {children}
      <div className="toolbar"><button type="button" onClick={onNext}>Skip</button></div>
    </section>
  );
}

function CreateAdmin({ onDone }: { onDone: () => void }) {
  const queryClient = useQueryClient();
  const [mismatch, setMismatch] = useState(false);
  const claim = useMutation({
    mutationFn: (body: { email: string; password: string }) => call(api.POST("/setup/admin", { body })),
    onSuccess: (user) => {
      queryClient.setQueryData(["me"], user);
      queryClient.setQueryData(["setup"], { needs_setup: false });
      onDone();
    },
    // Someone else claimed it: let /login stop redirecting back here.
    onError: (error) => {
      if (error instanceof ApiError && error.status === 409) queryClient.setQueryData(["setup"], { needs_setup: false });
    },
  });
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const password = String(f.get("password"));
    setMismatch(password !== String(f.get("repeat")));
    if (password === String(f.get("repeat"))) claim.mutate({ email: String(f.get("email")), password });
  };
  const taken = claim.error instanceof ApiError && claim.error.status === 409;
  return (
    <form className="panel sec" aria-labelledby="admin-h" onSubmit={submit}>
      <div className="sec-head"><h2 id="admin-h">Create the admin account</h2></div>
      <p className="hint">The first account is the administrator. Create it before you expose this site through Cloudflare Tunnel.</p>
      <label className="field"><span>Email</span><input name="email" type="email" required autoComplete="username" /></label>
      <label className="field"><span>Password</span><input name="password" type="password" required minLength={12} autoComplete="new-password" /></label>
      <label className="field"><span>Repeat password</span><input name="repeat" type="password" required minLength={12} autoComplete="new-password" /></label>
      {mismatch && <p className="error" role="alert">The passwords do not match.</p>}
      {claim.error && <p className="error" role="alert">{claim.error.message}{taken && <> <Link to="/login">Sign in</Link></>}</p>}
      <div className="toolbar"><button type="submit" className="primary" disabled={claim.isPending}>Create admin</button></div>
    </form>
  );
}
