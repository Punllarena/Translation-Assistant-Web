import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef } from "react";
import { api, call } from "../api/client";
import { actionOf, bindingOf, effective } from "./keymap";

export function useBindings() {
  const overrides = useQuery({ queryKey: ["shortcuts"], queryFn: () => call(api.GET("/shortcuts")) });
  return useMemo(() => effective(overrides.data ?? {}), [overrides.data]);
}

// Places that own their keys (find field, selects, dialogs, menus).
const OWN_KEYS = "input, select, textarea, dialog, [role=menu]";
// These own only Enter; line moves and the rest still work with focus on them.
const CONTROLS = "button, a, summary";

/** One window-level capture listener (the desktop _handle_key): a bound key runs its
 *  action before CodeMirror or the browser sees it. */
export function useEditorKeys(bindings: Record<string, string>, run: (action: string) => void, focusEditor: () => void) {
  const latest = useRef({ bindings, run, focusEditor });
  latest.current = { bindings, run, focusEditor };
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as Element | null;
      if (target?.closest?.(OWN_KEYS)) return;
      const onControl = Boolean(target?.closest?.(CONTROLS));
      const binding = bindingOf(e);
      const action = binding && !(onControl && binding === "Enter") && actionOf(latest.current.bindings, binding);
      if (!action) {
        if (target?.closest?.(".cm-editor")) return;
        // Focus strayed from the editor: Esc brings it back, and typing on the bare page lands in it.
        const typed = e.key === "Process" || (e.key.length === 1 && !e.ctrlKey && !e.altKey && !e.metaKey);
        if (e.key === "Escape" || (typed && !onControl)) latest.current.focusEditor();
        return;
      }
      e.preventDefault();
      e.stopPropagation();
      // A held Enter would skip lines unseen (ruling 8); other actions may repeat.
      if (e.repeat && action === "save_next") return;
      latest.current.run(action);
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, []);
}
