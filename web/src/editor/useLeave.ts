import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router";
import type { SaveState, SaveStore } from "./saveStore";

/**
 * Leave the chapter: flush first, and stay (with `notice`) while the last edits failed to save.
 * The notice clears when the next leave starts and when the save state is back to saved.
 */
export function useLeave(store: SaveStore, saveState: SaveState) {
  const navigate = useNavigate();
  const [notice, setNotice] = useState<string | null>(null);
  useEffect(() => {
    if (saveState === "saved") setNotice(null);
  }, [saveState]);
  const leave = useCallback(async (to: string) => {
    setNotice(null);
    await store.flush();
    if (store.getState().state === "error") {
      setNotice("Not moved: the last changes are not saved yet");
      return;
    }
    navigate(to);
  }, [store, navigate]);
  return { leave, notice };
}
