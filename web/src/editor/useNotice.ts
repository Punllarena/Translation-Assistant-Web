import { useCallback, useEffect, useState } from "react";

/** How long a status notice stays: long enough to read twice, short enough not to linger. */
const NOTICE_MS = 8000;

/** A status notice that clears itself, and at once when the line changes. */
export function useNotice(active: number): { notice: string | null; setNotice(text: string): void } {
  const [notice, setNotice] = useState<string | null>(null);
  useEffect(() => {
    setNotice(null);
  }, [active]);
  useEffect(() => {
    if (notice === null) return;
    const timer = setTimeout(() => setNotice(null), NOTICE_MS);
    return () => clearTimeout(timer);
  }, [notice]);
  const set = useCallback((text: string) => setNotice(text), []);
  return { notice, setNotice: set };
}
