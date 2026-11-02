import type { Schemas } from "../api/client";

/** What the site shows: the brand name and the ids of its images (camelCase of BrandingOut). */
export interface Branding {
  name: string;
  showName: boolean;
  logoId: number | null;
  logoDarkId: number | null;
  faviconId: number | null;
}

/** Nothing configured: the name, the 訳 mark in the header and the static 訳 favicon. */
export const DEFAULT_BRANDING: Branding = {
  name: "Translation Assistant",
  showName: true,
  logoId: null,
  logoDarkId: null,
  faviconId: null,
};

/** localStorage key: the last-seen branding, so the page paints before /branding arrives. */
export const BRAND_KEY = "ta.brand";

export function fromApi(body: Schemas["BrandingOut"]): Branding {
  return {
    name: body.name,
    showName: body.show_name,
    logoId: body.logo_id,
    logoDarkId: body.logo_dark_id,
    faviconId: body.favicon_id,
  };
}

export function imageUrl(id: number): string {
  return `/api/branding/image/${id}`;
}

const isId = (value: unknown): value is number | null =>
  value === null || (typeof value === "number" && Number.isInteger(value));

/** The cached branding, or null: missing, broken JSON, or not the shape we wrote. */
export function readCache(storage: Pick<Storage, "getItem">): Branding | null {
  try {
    const raw = storage.getItem(BRAND_KEY);
    if (raw === null) return null;
    const value: unknown = JSON.parse(raw);
    if (value === null || typeof value !== "object" || Array.isArray(value)) return null;
    const o = value as Record<string, unknown>;
    if (typeof o.name !== "string" || typeof o.showName !== "boolean") return null;
    if (!isId(o.logoId) || !isId(o.logoDarkId) || !isId(o.faviconId)) return null;
    return {
      name: o.name,
      showName: o.showName,
      logoId: o.logoId,
      logoDarkId: o.logoDarkId,
      faviconId: o.faviconId,
    };
  } catch {
    return null;
  }
}

export function writeCache(storage: Pick<Storage, "setItem">, brand: Branding): void {
  try {
    storage.setItem(BRAND_KEY, JSON.stringify(brand));
  } catch {
    // Blocked storage: the branding still applies for this page load.
  }
}

export function clearCache(storage: Pick<Storage, "removeItem">): void {
  try {
    storage.removeItem(BRAND_KEY);
  } catch {
    // Blocked storage: nothing to clear.
  }
}

/** The browser tab's title and icon: the uploaded favicon, else the static 訳 mark. */
export function headState(brand: Branding): { title: string; iconHref: string } {
  return {
    title: brand.name,
    iconHref: brand.faviconId === null ? "/favicon.svg" : imageUrl(brand.faviconId),
  };
}

/** What the header and the auth pages show: the 訳 mark when there is no logo, the name
 *  unless an admin hid it beside a logo, and the dark logo's url when one was uploaded. */
export function brandView(brand: Branding): {
  showMark: boolean;
  showName: boolean;
  logo: string | null;
  logoDark: string | null;
} {
  if (brand.logoId === null) {
    // A dark logo without a light one is not shown: there is nothing to swap it with.
    return { showMark: true, showName: true, logo: null, logoDark: null };
  }
  return {
    showMark: false,
    showName: brand.showName,
    logo: imageUrl(brand.logoId),
    logoDark: brand.logoDarkId === null ? null : imageUrl(brand.logoDarkId),
  };
}
