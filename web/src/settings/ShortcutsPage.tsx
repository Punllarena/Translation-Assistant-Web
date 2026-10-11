import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, call } from "../api/client";
import { ACTIONS, bindingOf, bindingProblem } from "../editor/keymap";
import { useBindings } from "../editor/useEditorKeys";

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
    <main>
      <h1>Keyboard shortcuts</h1>
      {error && <p className="error" role="alert">{error}</p>}
      <table>
        <thead><tr><th>Action</th><th>Key</th><th /></tr></thead>
        <tbody>
          {ACTIONS.map((a) => (
            <tr key={a.key}>
              <td>{a.label}</td>
              <td><kbd>{bindings[a.key]}</kbd></td>
              <td className="toolbar">
                <button onClick={() => { setProblem(null); setCapturing(a.key); }} disabled={bind.isPending}>
                  {capturing === a.key ? "Press a key… (Esc cancels)" : "Change"}
                </button>
                {bindings[a.key] !== a.binding && (
                  <button onClick={() => reset.mutate(a.key)} disabled={reset.isPending}>Reset to {a.binding}</button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}
