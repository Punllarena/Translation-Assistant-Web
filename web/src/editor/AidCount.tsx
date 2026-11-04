import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

/** Which aid cards can be used right now, so the collapsed column's peek bar can say
 *  "2 ready". Cards report through `useAidReady`; anything outside the provider is not counted. */
const Report = createContext<(key: string, ready: boolean) => void>(() => {});
const Count = createContext(0);

export function AidCount({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState<ReadonlySet<string>>(() => new Set());
  const report = useCallback((key: string, isReady: boolean) => {
    setReady((held) => {
      if (held.has(key) === isReady) return held;
      const next = new Set(held);
      if (isReady) next.add(key);
      else next.delete(key);
      return next;
    });
  }, []);
  return (
    <Report.Provider value={report}>
      <Count.Provider value={ready.size}>{children}</Count.Provider>
    </Report.Provider>
  );
}

/** Report this card's readiness while it is mounted; going away takes it back out. */
export function useAidReady(key: string, ready: boolean) {
  const report = useContext(Report);
  useEffect(() => {
    report(key, ready);
    return () => report(key, false);
  }, [key, ready, report]);
}

export const useAidCount = () => useContext(Count);
