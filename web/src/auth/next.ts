/** Where to go after signing in: an in-app path only, so ?next= cannot send anyone off-site. */
export function safeNext(next: string | null): string {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) return "/";
  if (/^\/(login|invite|setup)/.test(next)) return "/";
  return next;
}
