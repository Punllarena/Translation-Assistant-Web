/** A transport failure, as whole words: "abort", "dns" and "too long" are answers, not
 *  connections, so they stay as the backend said them. */
const NETWORK = /\b(failed to fetch|network ?error|econn(refused|reset)|enotfound|timed? out|timeout|unreachable|connection (refused|reset|closed))\b/i;
/** A rejected credential, however the backend spells it. */
const CREDENTIALS = /\b(401|403)\b|unauthori[sz]ed|forbidden|invalid[\s-]*(api[\s-]*)?(key|token)|authentication/i;

/** Turn a backend's failure message into what to do next, leaving any other message as it is.
 *  Pure, so the wording is tested without a card. */
export function friendlyError(message: string, backend = "the service"): string {
  if (CREDENTIALS.test(message)) return "Credentials rejected. Check them in Settings → Machine translation.";
  if (NETWORK.test(message)) return `Couldn't reach ${backend}. Retry, or check Settings → Machine translation.`;
  return message;
}
