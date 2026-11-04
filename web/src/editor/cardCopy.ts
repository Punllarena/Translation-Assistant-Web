/** The network-shaped failures an aid card can report: a refused connection, DNS,
 *  an abort, or the API's own timeout text. */
const NETWORK = /network|fetch|timed? ?out|timeout|too long|aborted|abort|econn|enotfound|dns|offline|unreachable/i;
/** A rejected credential, however the backend spells it. */
const CREDENTIALS = /\b(401|403)\b|unauthori[sz]ed|forbidden|invalid[\s-]*(api[\s-]*)?(key|token)|authentication/i;

/** Turn a backend's failure message into what to do next, leaving any other message as it is.
 *  Pure, so the wording is tested without a card. */
export function friendlyError(message: string, backend = "the service"): string {
  if (CREDENTIALS.test(message)) return "Credentials rejected. Check them in Settings → Machine translation.";
  if (NETWORK.test(message)) return `Couldn't reach ${backend}. Retry, or check Settings → Machine translation.`;
  return message;
}
