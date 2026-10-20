import { useQuery, type QueryClient } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { Navigate, Outlet, useLocation } from "react-router";
import { api, ApiError, call, type Schemas } from "../api/client";

export function useMe() {
  return useQuery({
    queryKey: ["me"],
    queryFn: async (): Promise<Schemas["UserOut"] | null> => {
      try {
        return await call(api.GET("/auth/me"));
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) return null;
        throw e;
      }
    },
    staleTime: Infinity,
  });
}

/** An expired session surfaces as a 401 on whatever request comes next. Marking the user
 *  signed out makes RequireAuth redirect to /login?next=<this page>. */
export function signedOutOn401(queryClient: QueryClient, error: unknown) {
  if (error instanceof ApiError && error.status === 401) queryClient.setQueryData(["me"], null);
}

/** Drop every cached query except ["me"] and ["setup"], whose observers (RequireAuth, SetupGate) must stay attached. */
export function forgetUserData(queryClient: QueryClient) {
  queryClient.removeQueries({ predicate: (q) => q.queryKey[0] !== "me" && q.queryKey[0] !== "setup" });
}

export function RequireAuth({ children }: { children: ReactNode }) {
  const me = useMe();
  const here = useLocation();
  if (me.isPending) return <p className="muted">Loading…</p>;
  if (me.isError) return <p className="error">{me.error.message}</p>;
  if (!me.data) {
    const next = encodeURIComponent(here.pathname + here.search);
    return <Navigate to={`/login?next=${next}`} replace />;
  }
  return children;
}

export function useSetupStatus() {
  return useQuery({
    queryKey: ["setup"],
    queryFn: () => call(api.GET("/setup/status")),
    staleTime: Infinity,
  });
}

/** While no account exists, every page is the setup wizard. */
export function SetupGate() {
  const setup = useSetupStatus();
  const here = useLocation();
  if (setup.isPending) return <p className="muted">Loading…</p>;
  if (setup.isError) return <p className="error">{setup.error.message}</p>;
  if (setup.data.needs_setup && here.pathname !== "/setup") return <Navigate to="/setup" replace />;
  return <Outlet />;
}
