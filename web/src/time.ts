/** The browser's IANA zone, sent as ?tz= / tz so the server judges "today" and "same day" as the user does. */
export const browserZone = (): string => Intl.DateTimeFormat().resolvedOptions().timeZone;

/** "YYYY-MM-DDTHH:MM" for <input type="datetime-local">, in local time. */
export function toLocalInput(d: Date): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

/** A datetime-local value (local time, no offset) as an ISO instant the API accepts. */
export const fromLocalInput = (value: string): string => new Date(value).toISOString();

/** The desktop dialogs' default slot: today at the default time (tomorrow if passed), else an hour from now. */
export function defaultSlot(defaultTime: string, now: Date = new Date()): Date {
  const m = /^(\d{2}):(\d{2})$/.exec(defaultTime);
  if (!m) return new Date(now.getTime() + 3_600_000);
  const d = new Date(now);
  d.setHours(Number(m[1]), Number(m[2]), 0, 0);
  if (d <= now) d.setDate(d.getDate() + 1);
  return d;
}
