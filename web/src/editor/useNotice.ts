import { useCallback, useEffect, useState, type ReactNode } from "react";

/** How long a status notice stays: long enough to read twice, short enough not to linger. */
const NOTICE_MS = 8000;

/** A status notice that clears itself, and at once when the line changes. It may carry an
 *  action (an Undo button), so it is a node, not only text. */
export function useNotice(active: number): { notice: ReactNode | null; setNotice(text: ReactNode): void } {
  const [notice, setNotice] = useState<ReactNode | null>(null);
  useEffect(() => {
    setNotice(null);
  }, [active]);
  useEffect(() => {
    if (notice === null) return;
    const timer = setTimeout(() => setNotice(null), NOTICE_MS);
    return () => clearTimeout(timer);
  }, [notice]);
  const set = useCallback((text: ReactNode) => setNotice(text), []);
  return { notice, setNotice: set };
}
