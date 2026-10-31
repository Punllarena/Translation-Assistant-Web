import { Outlet } from "react-router";
import { useMe } from "../auth/session";

/** One guard for the four /settings/admin/* routes: a non-admin sees the box, never a panel. */
export default function AdminOnly() {
  const me = useMe();
  if (me.isPending) return <p className="muted">Loading…</p>;
  if (!me.data?.is_admin) return <p className="box danger">Admin only.</p>;
  return <Outlet />;
}
