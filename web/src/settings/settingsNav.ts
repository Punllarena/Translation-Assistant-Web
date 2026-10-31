/** The sidebar's order, shared by the layout and its test. */
export type SettingsNavItem = { to: string; label: string };

/** Personal sections: the settings page every account owns. */
export const PERSONAL: SettingsNavItem[] = [
  { to: "/settings/editor", label: "Editor" },
  { to: "/settings/mt", label: "Machine translation" },
  { to: "/settings/wp", label: "WordPress" },
  { to: "/settings/shortcuts", label: "Shortcuts" },
];

/** Server-wide sections, shown only to admins. */
export const ADMIN: SettingsNavItem[] = [
  { to: "/settings/admin/server", label: "Server" },
  { to: "/settings/admin/invites", label: "Invites" },
  { to: "/settings/admin/dictionary", label: "Dictionary" },
  { to: "/settings/admin/backup", label: "Backup & restore" },
];

/** True for /settings and anything under it: the header keeps its one Settings link current. */
export function isSettingsPath(pathname: string): boolean {
  return pathname === "/settings" || pathname.startsWith("/settings/");
}
