/** The `ollama_schedule` user setting; the server's rules are `window_at` in api/ollama/schedule.py. */
export interface ScheduleValue {
  enabled: boolean;
  start: string; // "HH:MM"
  end: string;
  days: number[]; // 0 = Monday, the local day the window starts
  tz: string;
}

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
export const DAY_NAMES = DAYS;

/** Whether `tz` is an IANA zone this browser knows (the server checks with zoneinfo). */
export function validZone(tz: string): boolean {
  if (!tz.trim()) return false;
  try {
    new Intl.DateTimeFormat("en-US", { timeZone: tz.trim() });
    return true;
  } catch {
    return false;
  }
}

/** "01:00–07:00 · every night · Asia/Manila", or "Off". */
export function summary(s: ScheduleValue | undefined): string {
  if (!s || !s.enabled) return "Off";
  const days = s.days.length === 7 ? "every night" : s.days.length === 0 ? "no days"
    : [...s.days].sort((a, b) => a - b).map((d) => DAYS[d]).join(", ");
  return `${s.start}–${s.end} · ${days} · ${s.tz}`;
}

const parts = (at: Date, tz: string) => {
  const f = new Intl.DateTimeFormat("en-US", {
    timeZone: tz, hourCycle: "h23", year: "numeric", month: "numeric", day: "numeric",
    hour: "numeric", minute: "numeric", second: "numeric",
  });
  const get: Record<string, number> = {};
  for (const p of f.formatToParts(at)) if (p.type !== "literal") get[p.type] = Number(p.value);
  return get;
};

/** The instant at which the wall clock in `tz` reads y-m-d h:min. */
function zonedInstant(y: number, m: number, d: number, h: number, min: number, tz: string): Date {
  const wall = Date.UTC(y, m - 1, d, h, min);
  let guess = wall;
  for (let i = 0; i < 2; i++) {
    const p = parts(new Date(guess), tz);
    guess += wall - Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute, p.second);
  }
  return new Date(guess);
}

/** When the next window opens after `now` (a window that is open now does not count), or null
 *  when the schedule is off, has no days or names an unknown zone. Days are the local day the window starts. */
export function nextStart(s: ScheduleValue | undefined, now: Date): Date | null {
  if (!s || !s.enabled || s.days.length === 0 || !validZone(s.tz)) return null;
  const [h, min] = s.start.split(":").map(Number);
  const today = parts(now, s.tz);
  for (let offset = 0; offset <= 8; offset++) {
    const day = new Date(Date.UTC(today.year, today.month - 1, today.day + offset));
    const weekday = (day.getUTCDay() + 6) % 7;
    if (!s.days.includes(weekday)) continue;
    const start = zonedInstant(day.getUTCFullYear(), day.getUTCMonth() + 1, day.getUTCDate(), h, min, s.tz);
    if (start > now) return start;
  }
  return null;
}
