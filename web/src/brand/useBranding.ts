import { useQuery, type QueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { api, call } from "../api/client";
import {
  BRAND_KEY,
  DEFAULT_BRANDING,
  fromApi,
  headState,
  readCache,
  writeCache,
  type Branding,
} from "./brand";

const KEY = [BRAND_KEY] as const;
const STALE_MS = 5 * 60_000;

/** Storage can be missing or throw (private windows, blocked site data). */
function storage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

/** The site's branding: the cached copy paints first, /branding refreshes it, and a failure
 *  (signed out is fine; the route is public) falls back to the defaults, never a blank header. */
export function useBranding(): Branding {
  const query = useQuery({
    queryKey: KEY,
    queryFn: async () => {
      const brand = fromApi(await call(api.GET("/branding")));
      const store = storage();
      if (store) writeCache(store, brand);
      return brand;
    },
    initialData: () => {
      const store = storage();
      return (store && readCache(store)) || undefined;
    },
    // Mark the cached copy stale at once, so it paints immediately and is still revalidated;
    // the fresh answer then stays quiet for STALE_MS.
    initialDataUpdatedAt: 0,
    staleTime: STALE_MS,
  });
  return query.data ?? DEFAULT_BRANDING;
}

/** Keep the tab's title and icon in step with the branding. Called once, above every route. */
export function useBrandHead(): void {
  const brand = useBranding();
  useEffect(() => {
    const { title, iconHref } = headState(brand);
    document.title = title;
    let link = document.querySelector<HTMLLinkElement>('link[rel="icon"]');
    if (!link) {
      link = document.createElement("link");
      link.rel = "icon";
      document.head.appendChild(link);
    }
    link.href = iconHref;
    if (brand.faviconId === null) link.type = "image/svg+xml";
    else link.removeAttribute("type"); // an upload may be a PNG, WebP or ICO
  }, [brand]);
}

/** Fetch the branding again after an admin change (the panel calls it after every write). */
export function invalidateBranding(queryClient: QueryClient): void {
  void queryClient.invalidateQueries({ queryKey: KEY });
}
