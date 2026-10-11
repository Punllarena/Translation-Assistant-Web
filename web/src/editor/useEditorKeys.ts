import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef } from "react";
import { api, call } from "../api/client";
import { actionOf, bindingOf, effective } from "./keymap";

export function useBindings() {
  const overrides = useQuery({ queryKey: ["shortcuts"], queryFn: () => call(api.GET("/shortcuts")) });
  return useMemo(() => effective(overrides.data ?? {}), [overrides.data]);
}

// Controls that own their keys (find field, selects, buttons, the spell menu).
const OWN_KEYS = "input, select, textarea, button, a, summary, [role=menu]";

/** One window-level capture listener (the desktop _handle_key): a bound key runs its
 *  action before CodeMirror or the browser sees it. */
export function useEditorKeys(bindings: Record<string, string>, run: (action: string) => void) {
  const latest = useRef({ bindings, run });
  latest.current = { bindings, run };
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as Element | null)?.closest?.(OWN_KEYS)) return;
      const binding = bindingOf(e);
      const action = binding && actionOf(latest.current.bindings, binding);
      if (!action) return;
      e.preventDefault();
      e.stopPropagation();
      latest.current.run(action);
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, []);
}
