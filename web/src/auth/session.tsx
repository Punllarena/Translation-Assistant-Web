import { useQuery, type QueryClient } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router";
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

/** Drop every cached query except ["me"], whose observer (RequireAuth) must stay attached. */
export function forgetUserData(queryClient: QueryClient) {
  queryClient.removeQueries({ predicate: (q) => q.queryKey[0] !== "me" });
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
