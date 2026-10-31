import { NavLink, Outlet } from "react-router";
import { useMe } from "../auth/session";
import { ADMIN, PERSONAL } from "./settingsNav";

/** One settings page: the sidebar on the left, the chosen section on the right. */
export default function SettingsLayout() {
  const me = useMe();
  return (
    <main className="settings-layout">
      <nav className="settings-nav" aria-label="Settings">
        {PERSONAL.map((item) => <NavLink key={item.to} to={item.to}>{item.label}</NavLink>)}
        {me.data?.is_admin && (
          <>
            <span className="settings-nav-heading">Admin</span>
            {ADMIN.map((item) => <NavLink key={item.to} to={item.to}>{item.label}</NavLink>)}
          </>
        )}
      </nav>
      <div className="settings-content"><Outlet /></div>
    </main>
  );
}
