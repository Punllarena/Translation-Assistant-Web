import { useCallback } from "react";
import { useNavigate } from "react-router";
import type { SaveStore } from "./saveStore";

/** Leave the chapter: flush first, and stay (with a notice) while the last edits failed to save. */
export function useLeave(store: SaveStore, setNotice: (message: string | null) => void) {
  const navigate = useNavigate();
  return useCallback(async (to: string) => {
    await store.flush();
    if (store.getState().state === "error") {
      setNotice("Not moved: the last changes are not saved yet");
      return;
    }
    navigate(to);
  }, [store, setNotice, navigate]);
}
