import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useBlocker } from "react-router";
import { api, call, type Schemas } from "../api/client";
import GlossaryTable from "./GlossaryTable";

/** Profiles (name, parse characters) and the selected profile's glossary. */
export default function ProfilesPage() {
  const queryClient = useQueryClient();
  const profiles = useQuery({ queryKey: ["profiles"], queryFn: () => call(api.GET("/profiles")) });
  const [chosen, setChosen] = useState<number | null>(null);
  const [dirty, setDirty] = useState(false); // unsaved glossary edits
  const list = profiles.data ?? [];
  const discardOk = () => !dirty || window.confirm("Discard unsaved glossary edits?");
  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
  const blocker = useBlocker(({ currentLocation, nextLocation }) =>
    dirty && currentLocation.pathname !== nextLocation.pathname
    // a sign-out redirect must not be held up
    && !nextLocation.pathname.startsWith("/login"));
  useEffect(() => {
    if (blocker.state !== "blocked") return;
    if (window.confirm("Discard unsaved glossary edits?")) blocker.proceed();
    else blocker.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only re-ask when the state changes
  }, [blocker.state]);
  const current = list.find((p) => p.id === chosen) ?? list.find((p) => p.is_default) ?? list[0];
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["profiles"] });
  const create = useMutation({
    mutationFn: (name: string) => call(api.POST("/profiles", { body: { name } as Schemas["ProfileCreate"] })),
    onSuccess: (p) => { setChosen(p.id); refresh(); },
  });
  const patch = useMutation({
    mutationFn: (body: { name?: string; parse_chars?: string }) =>
      call(api.PATCH("/profiles/{profile_id}", { params: { path: { profile_id: current!.id } }, body })),
    onSuccess: refresh,
  });
  const remove = useMutation({
    mutationFn: () => call(api.DELETE("/profiles/{profile_id}", { params: { path: { profile_id: current!.id } } })),
    onSuccess: () => { setChosen(null); refresh(); },
  });
  const error = profiles.error?.message ?? create.error?.message ?? patch.error?.message ?? remove.error?.message;
  return (
    <main>
      <h1>Profiles</h1>
      {error && <p className="error" role="alert">{error}</p>}
      {current && (
        <>
          <div className="toolbar">
            <select aria-label="Profile" value={current.id} onChange={(e) => { if (discardOk()) setChosen(Number(e.target.value)); }}>
              {list.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
            <button onClick={() => { if (!discardOk()) return; const n = window.prompt("Profile name"); if (n?.trim()) create.mutate(n.trim()); }}>New profile</button>
            <button onClick={() => { const n = window.prompt("New name", current.name); if (n?.trim()) patch.mutate({ name: n.trim() }); }}>Rename</button>
            <button onClick={() => { if (window.confirm(`Delete profile "${current.name}"?`) && discardOk()) remove.mutate(); }}>Delete</button>
          </div>
          <form
            key={`${current.id}:${current.parse_chars}`}
            className="toolbar"
            onSubmit={(e) => {
              e.preventDefault();
              patch.mutate({ parse_chars: new FormData(e.currentTarget).get("parse_chars") as string });
            }}
          >
            <label>Parse characters <input name="parse_chars" defaultValue={current.parse_chars} /></label>
            <button type="submit" disabled={patch.isPending}>Save</button>
          </form>
          <h2>Glossary</h2>
          <GlossaryTable pid={current.id} onDirty={setDirty} />
        </>
      )}
    </main>
  );
}
