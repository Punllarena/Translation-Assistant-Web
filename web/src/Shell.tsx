import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, NavLink, Outlet, useLocation } from "react-router";
import { api, call } from "./api/client";
import { forgetUserData, useMe } from "./auth/session";
import RunningJobs from "./jobs/RunningJobs";
import ThemeMenu from "./theme/ThemeMenu";
import { useThemeSync } from "./theme/useThemeSync";

/** The Library link stays marked inside a series, a chapter and the import page. */
const LIBRARY = /^\/($|series\/|documents\/|import$)/;

export default function Shell() {
  const me = useMe();
  const queryClient = useQueryClient();
  const { pathname } = useLocation();
  useThemeSync();
  const logout = useMutation({
    mutationFn: () => call(api.POST("/auth/logout")),
    onSuccess: () => {
      forgetUserData(queryClient);
      queryClient.setQueryData(["me"], null);
    },
  });
  return (
    <>
      <header className="app-header">
        <Link className="brand" to="/"><span className="mark" aria-hidden="true">訳</span>Translation Assistant</Link>
        <nav aria-label="Main">
          <Link to="/" aria-current={LIBRARY.test(pathname) ? "page" : undefined}>Library</Link>
          <NavLink to="/stats">Statistics</NavLink>
          <NavLink to="/settings/profiles">Profiles</NavLink>
          <NavLink to="/settings/mt">Machine translation</NavLink>
          <NavLink to="/settings/wp">WordPress</NavLink>
          <NavLink to="/settings/shortcuts">Shortcuts</NavLink>
          {me.data?.is_admin && <NavLink to="/admin">Admin</NavLink>}
        </nav>
        <div className="who">
          <RunningJobs />
          <ThemeMenu />
          <span className="email" title={me.data?.email}>{me.data?.username}</span>
          <button type="button" className="quiet" onClick={() => logout.mutate()}>Sign out</button>
        </div>
      </header>
      <Outlet />
    </>
  );
}
