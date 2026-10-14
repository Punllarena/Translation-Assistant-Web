import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useBlocker } from "react-router";
import { api, call, type Schemas } from "../api/client";
import PageHeader from "../ui/PageHeader";
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
  const newProfile = () => {
    if (!discardOk()) return;
    const name = window.prompt("Profile name");
    if (name?.trim()) create.mutate(name.trim());
  };
  return (
    <main className="with-rail">
      <aside className="rail" aria-label="Profiles">
        <div className="rail-head">
          <h2 className="label">Profiles</h2>
          <button type="button" onClick={newProfile}>New profile</button>
        </div>
        <ul>
          {list.map((p) => (
            <li key={p.id}>
              <button type="button" className="rail-item" aria-current={current?.id === p.id ? "true" : undefined}
                onClick={() => { if (p.id !== current?.id && discardOk()) setChosen(p.id); }}>
                <span>{p.name}</span>{p.is_default && <span className="pill">Default</span>}
              </button>
            </li>
          ))}
        </ul>
      </aside>
      <div className="rail-main">
        {error && <p className="error" role="alert">{error}</p>}
        {current && (
          <>
            <PageHeader title={current.name} actions={<>
              <button type="button" onClick={() => { const name = window.prompt("New name", current.name); if (name?.trim()) patch.mutate({ name: name.trim() }); }}>Rename</button>
              <button type="button" className="danger" onClick={() => { if (window.confirm(`Delete profile "${current.name}"?`) && discardOk()) remove.mutate(); }}>Delete</button>
            </>} />
            <form
              key={`${current.id}:${current.parse_chars}`}
              className="panel sec parse-form"
              onSubmit={(e) => {
                e.preventDefault();
                patch.mutate({ parse_chars: new FormData(e.currentTarget).get("parse_chars") as string });
              }}
            >
              <label className="field">
                <span>Parse characters</span>
                <input name="parse_chars" className="mono" defaultValue={current.parse_chars} aria-describedby="parse-hint" />
              </label>
              <button type="submit" disabled={patch.isPending}>Save</button>
              <p id="parse-hint" className="hint">Characters that end a phrase for Next phrase and Previous phrase.</p>
            </form>
            <GlossaryTable pid={current.id} onDirty={setDirty} />
          </>
        )}
      </div>
    </main>
  );
}
