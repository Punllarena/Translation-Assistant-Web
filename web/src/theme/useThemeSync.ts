import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { api, call } from "../api/client";
import { applyPref, parseThemePref } from "./theme";

/** Once settings arrive, the account's ui_theme replaces this device's copy (another device may have changed it). */
export function useThemeSync(): void {
  const settings = useQuery({ queryKey: ["settings"], queryFn: () => call(api.GET("/settings")) });
  const loaded = settings.isSuccess;
  const value = settings.data?.ui_theme;
  useEffect(() => {
    if (loaded) applyPref(parseThemePref(value));
  }, [loaded, value]);
}
