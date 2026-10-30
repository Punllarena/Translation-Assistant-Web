import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, call } from "../api/client";

export interface AccountPrefOptions<T> {
  /** The `/settings` key. */
  key: string;
  /** The localStorage key the page paints from before /settings arrives. */
  local: string;
  parse: (value: unknown) => T;
  fallback: T;
}

/** Storage can be missing or throw (private windows, blocked site data). */
function stored(local: string): unknown {
  try {
    const raw = window.localStorage.getItem(local);
    return raw === null ? undefined : JSON.parse(raw);
  } catch {
    return undefined;
  }
}

function mirror(local: string, value: unknown): void {
  try {
    window.localStorage.setItem(local, JSON.stringify(value));
  } catch {
    // Blocked storage: the choice still applies for this page load.
  }
}

/** A preference the account owns, with a localStorage copy so the page paints before
 *  `/settings` arrives. The account's value wins once it does; when only this browser has one
 *  it is written up once (the migration of spec §5). `set` writes both and the settings cache.
 *  Uses the same query key and fetch as `useThemeSync`. */
export function useAccountPref<T>(o: AccountPrefOptions<T>): [T, (value: T) => void] {
  const { key, local, parse } = o;
  const queryClient = useQueryClient();
  const [value, setValue] = useState<T>(() => {
    const raw = stored(local);
    return raw === undefined ? o.fallback : parse(raw);
  });
  const settings = useQuery({ queryKey: ["settings"], queryFn: () => call(api.GET("/settings")) });
  const loaded = settings.isSuccess;
  const account = settings.data?.[key];
  const pushed = useRef(false);
  const push = useCallback(
    (v: T) => {
      const cached = queryClient.getQueryData<Record<string, unknown>>(["settings"]) ?? {};
      queryClient.setQueryData(["settings"], { ...cached, [key]: v });
      return call(api.PUT("/settings", { body: { [key]: v } }))
        .then((data) => queryClient.setQueryData(["settings"], data))
        .catch(() => undefined); // a failed write leaves the local copy in charge
    },
    [key, queryClient],
  );
  useEffect(() => {
    if (!loaded) return;
    if (account === undefined || account === null) {
      const raw = stored(local);
      if (raw !== undefined && !pushed.current) {
        pushed.current = true;
        void push(parse(raw));
      }
      return;
    }
    const parsed = parse(account);
    setValue(parsed);
    mirror(local, parsed);
  }, [loaded, account, local, parse, push]);
  const set = useCallback(
    (v: T) => {
      setValue(v);
      mirror(local, v);
      void push(v);
    },
    [local, push],
  );
  return [value, set];
}
