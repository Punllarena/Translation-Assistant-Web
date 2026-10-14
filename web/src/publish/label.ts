/** The confirm button. "Anyway" appears only while the previous chapter is still scheduled (spec §9.4). */
export function confirmLabel(previousScheduled: boolean, scheduling: boolean): string {
  if (!previousScheduled) return "Publish";
  return scheduling ? "Schedule anyway" : "Publish anyway";
}

/** Badge tone for a WordPress status. */
export function statusTone(status: string): "ok" | "warn" | "" {
  if (status === "publish") return "ok";
  if (status === "future") return "warn";
  return "";
}
