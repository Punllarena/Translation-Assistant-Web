import { useMutation, useQueryClient } from "@tanstack/react-query";
import { NavLink, Outlet } from "react-router";
import { api, call } from "./api/client";
import { forgetUserData, useMe } from "./auth/session";

export default function Shell() {
  const me = useMe();
  const queryClient = useQueryClient();
  const logout = useMutation({
    mutationFn: () => call(api.POST("/auth/logout")),
    onSuccess: () => {
      forgetUserData(queryClient);
      queryClient.setQueryData(["me"], null);
    },
  });
  return (
    <>
      <header className="app">
        <nav>
          <NavLink to="/">Library</NavLink>
          <NavLink to="/settings/profiles">Profiles</NavLink>
          <NavLink to="/settings/mt">Machine translation</NavLink>
          <NavLink to="/settings/wp">WordPress</NavLink>
          <NavLink to="/settings/shortcuts">Shortcuts</NavLink>
        </nav>
        <span className="muted">{me.data?.email}</span>
        <button onClick={() => logout.mutate()}>Sign out</button>
      </header>
      <Outlet />
    </>
  );
}
