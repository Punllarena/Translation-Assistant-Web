/** A transport failure, as whole words: "abort", "dns" and "too long" are answers, not
 *  connections, so they stay as the backend said them. */
const NETWORK = /\b(failed to fetch|network ?error|econn(refused|reset)|enotfound|timed? out|timeout|unreachable|connection (refused|reset|closed))\b/i;
/** A rejected credential, however the backend spells it. */
const CREDENTIALS = /\b(401|403)\b|unauthori[sz]ed|forbidden|invalid[\s-]*(api[\s-]*)?(key|token)|authentication/i;

/** Turn a backend's failure message into what to do next, leaving any other message as it is.
 *  `settingsHint` is for the machine-translation card: translation memory has no URL or
 *  credentials of its own, so pointing at Settings → Machine translation would be wrong. Pure,
 *  so the wording is tested without a card. */
export function friendlyError(message: string, backend = "the service", settingsHint = true): string {
  if (CREDENTIALS.test(message)) {
    return settingsHint ? "Credentials rejected. Check them in Settings → Machine translation." : "Credentials rejected.";
  }
  if (NETWORK.test(message)) {
    return `Couldn't reach ${backend}. Retry${settingsHint ? ", or check Settings → Machine translation" : ""}.`;
  }
  return message;
}
