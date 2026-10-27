import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, call } from "../api/client";
import { browserZone } from "../time";
import type { ScheduleValue } from "./schedule";

/** The `ollama_schedule` setting as a ScheduleValue; undefined while unset or malformed. */
export function asSchedule(v: unknown): ScheduleValue | undefined {
  if (!v || typeof v !== "object") return undefined;
  const s = v as Record<string, unknown>;
  if (typeof s.start !== "string" || typeof s.end !== "string" || typeof s.tz !== "string" || !Array.isArray(s.days)) return undefined;
  return { enabled: s.enabled === true, start: s.start, end: s.end, days: s.days.filter((d): d is number => typeof d === "number"), tz: s.tz };
}

export const defaultSchedule = (): ScheduleValue => ({
  enabled: true, start: "01:00", end: "07:00", days: [0, 1, 2, 3, 4, 5, 6], tz: browserZone(),
});

export function useSchedule() {
  const queryClient = useQueryClient();
  const settings = useQuery({ queryKey: ["settings"], queryFn: () => call(api.GET("/settings")) });
  const save = useMutation({
    mutationFn: (value: ScheduleValue) => call(api.PUT("/settings", { body: { ollama_schedule: value } })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["settings"] }),
  });
  return { schedule: asSchedule(settings.data?.ollama_schedule), loading: settings.isPending, error: settings.error, save };
}
