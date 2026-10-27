import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, call } from "../api/client";
import { QUEUE_KEY } from "../jobs/AddToQueueDialog";

type QueueBody = { kind: "series" | "volume" | "documents"; series_id: number; volume_id?: number | null; document_ids?: number[] };
type FlushBody = { document_ids?: number[]; volume_id?: number; series_id?: number };

/** Queue chapters, a volume or a series for Ollama. `note` is "Queued for Ollama"; `error` is the API's message (409 at the cap). */
export function useQueueOllama() {
  const queryClient = useQueryClient();
  const queue = useMutation({
    mutationFn: (body: QueueBody) => call(api.POST("/ollama/queue", { body })),
    onSettled: () => queryClient.invalidateQueries({ queryKey: QUEUE_KEY }),
  });
  const note = queue.isSuccess ? "Queued for Ollama" : null;
  return { queue: queue.mutate, pending: queue.isPending, note, error: queue.error?.message ?? null };
}

/** Clear Ollama's saved suggestions for chapters; the caller confirms first. */
export function useFlushOllama(onDone?: (cleared: number) => void) {
  const flush = useMutation({
    mutationFn: (body: FlushBody) => call(api.POST("/ollama/flush", { body })),
    onSuccess: (data) => onDone?.(data.cleared),
  });
  return { flush: flush.mutate, pending: flush.isPending, error: flush.error?.message ?? null, reset: flush.reset };
}
