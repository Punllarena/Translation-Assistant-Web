import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { api, call, type Schemas } from "../api/client";

type Invite = Schemas["InviteOut"];

function state(i: Invite): "used" | "expired" | "pending" {
  if (i.accepted_at) return "used";
  return new Date(i.expires_at) <= new Date() ? "expired" : "pending";
}

export default function InvitesPanel() {
  const queryClient = useQueryClient();
  const [link, setLink] = useState("");
  const list = useQuery({ queryKey: ["admin", "invites"], queryFn: () => call(api.GET("/invites")) });
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["admin", "invites"] });
  const create = useMutation({
    mutationFn: (body: { email?: string; ttl_days: number }) => call(api.POST("/invites", { body })),
    onSuccess: (r) => { setLink(`${location.origin}/invite?token=${encodeURIComponent(r.token)}`); void refresh(); },
  });
  const revoke = useMutation({
    mutationFn: (invite_id: number) => call(api.DELETE("/invites/{invite_id}", { params: { path: { invite_id } } })),
    onSuccess: refresh,
  });
  const submit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const email = String(f.get("email") ?? "").trim();
    create.mutate({ ...(email ? { email } : {}), ttl_days: Number(f.get("ttl")) });
  };
  const error = list.error ?? create.error ?? revoke.error;
  return (
    <section className="panel sec" aria-labelledby="invites-h">
      <div className="sec-head"><h2 id="invites-h">Invites</h2></div>
      <form onSubmit={submit} aria-label="Create invite">
        <label className="field"><span>Email (optional)</span><input name="email" type="email" /></label>
        <label className="field"><span>Valid for (days)</span><input name="ttl" type="number" min={1} max={90} defaultValue={14} /></label>
        <div className="toolbar"><button type="submit" className="primary" disabled={create.isPending}>Create invite</button></div>
      </form>
      {link && (
        <p className="box ok" role="status">Send this link; it is shown only once.<br />
          <input className="mono" readOnly value={link} aria-label="Invite link" onFocus={(e) => e.currentTarget.select()} />
          <button type="button" onClick={() => void navigator.clipboard?.writeText(link)}>Copy</button></p>
      )}
      {error && <p className="error" role="alert">{error.message}</p>}
      {list.data && list.data.length > 0 && (
        <table>
          <thead><tr><th>Email</th><th>Expires</th><th>Status</th><th /></tr></thead>
          <tbody>
            {list.data.map((i) => (
              <tr key={i.id}>
                <td>{i.email ?? <span className="muted">anyone</span>}</td>
                <td>{new Date(i.expires_at).toLocaleDateString()}</td>
                <td>{state(i)}</td>
                <td>{state(i) === "pending" && <button type="button" onClick={() => revoke.mutate(i.id)}>Revoke</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
