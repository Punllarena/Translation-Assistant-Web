export type ThemePref = "system" | "light" | "dark";
export type Theme = "light" | "dark";

/** localStorage key. index.html's inline script reads the same key before the bundle loads. */
export const THEME_KEY = "ta.theme";
export const THEME_PREFS: readonly ThemePref[] = ["system", "light", "dark"];

/** Any stored or server value to a preference; unknown values mean "system". */
export function parseThemePref(value: unknown): ThemePref {
  return value === "light" || value === "dark" ? value : "system";
}

export function resolveTheme(pref: ThemePref, systemDark: boolean): Theme {
  if (pref === "system") return systemDark ? "dark" : "light";
  return pref;
}

/** Storage can be missing or throw (private windows, blocked site data). */
export function readPref(storage: Pick<Storage, "getItem"> | null): ThemePref {
  try {
    return parseThemePref(storage?.getItem(THEME_KEY));
  } catch {
    return "system";
  }
}

function browserStorage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

const darkQuery = () => window.matchMedia("(prefers-color-scheme: dark)");

export const storedPref = (): ThemePref => readPref(browserStorage());

/** Remember the preference on this device and paint it. */
export function applyPref(pref: ThemePref): void {
  try {
    browserStorage()?.setItem(THEME_KEY, pref);
  } catch {
    // Blocked storage: the theme still applies for this page load.
  }
  document.documentElement.dataset.theme = resolveTheme(pref, darkQuery().matches);
}

/** Paint the stored preference and follow the OS while it is "system". Call once at startup. */
export function startTheme(): void {
  applyPref(storedPref());
  darkQuery().addEventListener("change", () => applyPref(storedPref()));
}
