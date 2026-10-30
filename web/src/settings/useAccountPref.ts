import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api, call } from "../api/client";

export interface AccountPrefOptions<T> {
  /** The `/settings` key. */
  key: string;
  /** The localStorage key the page paints from before /settings arrives. */
  local: string;
  /** How the localStorage copy is encoded. `ta.libraryView` has always held a bare string
   *  (`shelf` / `list`), so it asks for `text`; everything else is JSON. */
  localFormat?: "json" | "text";
  parse: (value: unknown) => T;
  fallback: T;
}

export interface ResolvedPref<T> {
  value: T;
  /** The browser's value to write up, or null: the account already has one, or there is none. */
  upload: T | null;
}

/** The rule the hook and the first-load migration follow: the account's value wins; with no
 *  account value and one on this browser, the browser's is used and uploaded; else the fallback. */
export function resolvePref<T>(
  account: unknown, hasAccount: boolean, local: T | null,
  parse: (value: unknown) => T, fallback: T,
): ResolvedPref<T> {
  if (hasAccount) return { value: parse(account), upload: null };
  return local === null ? { value: fallback, upload: null } : { value: local, upload: local };
}

/** The part of the options the localStorage copy needs (kept separate so the effect can depend
 *  on its fields and not on the options object, which callers rebuild each render). */
interface LocalCopy<T> {
  local: string;
  localFormat?: "json" | "text";
  parse: (value: unknown) => T;
}

/** Storage can be missing or throw (private windows, blocked site data). */
function readLocal<T>(o: LocalCopy<T>): T | null {
  try {
    const raw = window.localStorage.getItem(o.local);
    if (raw === null) return null;
    return o.parse(o.localFormat === "text" ? raw : JSON.parse(raw));
  } catch {
    return null;
  }
}

function mirror<T>(o: Pick<LocalCopy<T>, "local" | "localFormat">, value: T): void {
  try {
    const raw = o.localFormat === "text" ? String(value) : JSON.stringify(value);
    window.localStorage.setItem(o.local, raw);
  } catch {
    // Blocked storage: the choice still applies for this page load.
  }
}

/** A preference the account owns, with a localStorage copy so the page paints before
 *  `/settings` arrives. The account's value wins once it does; when only this browser has one
 *  it is written up once (the migration of spec §5), unless the user has already changed it or
 *  `/settings` failed. `set` writes both, optimistically updates the settings cache and queues
 *  one PUT. Uses the same query key and fetch as `useThemeSync`. */
export function useAccountPref<T>(o: AccountPrefOptions<T>): [T, (value: T) => void] {
  const { key, local, parse, fallback, localFormat } = o;
  const queryClient = useQueryClient();
  const [value, setValue] = useState<T>(() => readLocal(o) ?? fallback);
  const settings = useQuery({ queryKey: ["settings"], queryFn: () => call(api.GET("/settings")) });
  const touched = useRef(false);
  const migrated = useRef(false);
  const { mutate: push } = useMutation({
    // One write at a time per key, in call order: the migration PUT can never land after the
    // user's explicit change, and two quick clicks leave the last choice on the account.
    scope: { id: key },
    mutationFn: (v: T) => call(api.PUT("/settings", { body: { [key]: v } })),
    // Keep the latest choice visible: a stale GET or an earlier PUT's response must not win.
    onMutate: (v) => {
      queryClient.setQueryData<Record<string, unknown>>(
        ["settings"], (cached) => ({ ...cached, [key]: v }),
      );
    },
  });
  useEffect(() => {
    // A load that began before the user's change must not overwrite it (the change's own PUT
    // carries the newest value), and a failed load is no reason to write anything up.
    if (!settings.isSuccess || touched.current || migrated.current) return;
    const account = settings.data?.[key];
    const hasAccount = account !== undefined && account !== null;
    const resolved = resolvePref(account, hasAccount, readLocal({ local, localFormat, parse }),
      parse, fallback);
    if (resolved.upload !== null) {
      migrated.current = true;
      push(resolved.upload);
    }
    if (hasAccount) {
      setValue(resolved.value);
      mirror({ local, localFormat }, resolved.value);
    }
  }, [settings.isSuccess, settings.data, key, local, localFormat, parse, fallback, push]);
  const set = (v: T) => {
    touched.current = true;
    setValue(v);
    mirror({ local, localFormat }, v);
    push(v);
  };
  return [value, set];
}
