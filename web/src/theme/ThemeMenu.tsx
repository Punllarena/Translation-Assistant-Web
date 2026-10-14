import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, call } from "../api/client";
import Menu from "../ui/Menu";
import { applyPref, parseThemePref, storedPref, THEME_PREFS, type ThemePref } from "./theme";

const LABEL: Record<ThemePref, string> = { system: "System", light: "Light", dark: "Dark" };

function Icon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <circle cx="8" cy="8" r="5.5" />
      <path d="M8 2.5v11a5.5 5.5 0 0 0 0-11z" fill="currentColor" />
    </svg>
  );
}

/** Header control: System / Light / Dark, saved to the account (ui_theme) and to this device. */
export default function ThemeMenu() {
  const queryClient = useQueryClient();
  const settings = useQuery({ queryKey: ["settings"], queryFn: () => call(api.GET("/settings")) });
  const pref = settings.isSuccess ? parseThemePref(settings.data.ui_theme) : storedPref();
  const save = useMutation({
    mutationFn: (p: ThemePref) => call(api.PUT("/settings", { body: { ui_theme: p } })),
    onSuccess: (data) => queryClient.setQueryData(["settings"], data),
    // A failed save: reload the account's value, which useThemeSync then paints.
    onError: () => queryClient.invalidateQueries({ queryKey: ["settings"] }),
  });
  const choose = (p: ThemePref) => {
    applyPref(p);
    queryClient.setQueryData(["settings"], { ...settings.data, ui_theme: p });
    save.mutate(p);
  };
  return (
    <Menu label={<><Icon />{LABEL[pref]}</>} buttonLabel={`Theme: ${LABEL[pref]}`}>
      {(close) => THEME_PREFS.map((p) => (
        <button key={p} type="button" role="menuitemradio" aria-checked={p === pref}
          onClick={() => { choose(p); close(); }}>
          {LABEL[p]}
        </button>
      ))}
    </Menu>
  );
}
