import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, call } from "../api/client";
import { ACTIONS, bindingOf, bindingProblem } from "../editor/keymap";
import { useBindings } from "../editor/useEditorKeys";
import PageHeader from "../ui/PageHeader";
import { groupActions } from "./shortcutGroups";

/** Rebind editor keys (desktop dlg_shortcuts): press "Change", then the new key. */
export default function ShortcutsPage() {
  const queryClient = useQueryClient();
  const bindings = useBindings();
  const [capturing, setCapturing] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["shortcuts"] });
  const bind = useMutation({
    mutationFn: ({ action, binding }: { action: string; binding: string }) =>
      call(api.PUT("/shortcuts", { body: { [action]: binding } })),
    onSuccess: refresh,
  });
  const reset = useMutation({
    mutationFn: (action: string) =>
      call(api.DELETE("/shortcuts/{action_key}", { params: { path: { action_key: action } } })),
    onSuccess: refresh,
  });
  useEffect(() => {
    if (!capturing) return;
    const onKey = (e: KeyboardEvent) => {
      e.preventDefault();
      e.stopPropagation();
      if (e.key === "Escape") return setCapturing(null);
      const binding = bindingOf(e);
      if (!binding) return; // a bare modifier: wait for the key
      const why = bindingProblem(bindings, capturing, binding);
      setProblem(why);
      if (!why) bind.mutate({ action: capturing, binding });
      setCapturing(null);
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [capturing, bindings, bind]);
  const error = problem ?? bind.error?.message ?? reset.error?.message;
  return (
    <main className="settings">
      <PageHeader title="Keyboard shortcuts" subtitle="Editor keys. Press Change, then the new key; Esc cancels." />
      {error && <p className="box danger" role="alert">{error}</p>}
      <div className="shortcut-groups">
        {groupActions(ACTIONS).map((g, gi) => (
          <section key={g.title} className="panel" aria-labelledby={`sc-group-${gi}`}>
            <h2 id={`sc-group-${gi}`} className="label panel-label">{g.title}</h2>
            <ul className="shortcut-list">
              {g.actions.map((a) => {
                const here = capturing === a.key;
                const changed = bindings[a.key] !== a.binding;
                return (
                  <li key={a.key} className={here ? "capturing" : undefined}>
                    <span>
                      {a.label}
                      {changed && <><span className="dot accent" aria-hidden="true" /><span className="visually-hidden"> (changed)</span></>}
                    </span>
                    <kbd>{here ? "Press a key…" : bindings[a.key]}</kbd>
                    <span className="sc-actions">
                      <button type="button" className="small" disabled={bind.isPending}
                        onClick={() => { setProblem(null); setCapturing(here ? null : a.key); }}>
                        {here ? "Cancel" : "Change"}
                      </button>
                      {changed && (
                        <button type="button" className="small quiet" title={`Reset to ${a.binding}`} aria-label={`Reset to ${a.binding}`}
                          disabled={reset.isPending} onClick={() => reset.mutate(a.key)}>Reset</button>
                      )}
                    </span>
                  </li>
                );
              })}
            </ul>
          </section>
        ))}
      </div>
    </main>
  );
}
