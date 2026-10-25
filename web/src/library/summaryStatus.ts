export type SummaryTone = "muted" | "ok" | "error";

/** The status line under the series summary box. */
export function summaryStatus(s: { text: string; pending: boolean; error: string }): { tone: SummaryTone; message: string } {
  if (!s.text.trim()) {
    return { tone: "muted", message: "Not set. Clearing it does not remove the summary already on WordPress." };
  }
  if (s.pending && s.error) {
    return { tone: "error", message: `Last send failed: ${s.error}. It will be tried again with the next chapter you publish.` };
  }
  if (s.pending) return { tone: "muted", message: "Waiting: goes out with the next chapter you publish." };
  return { tone: "ok", message: "On WordPress." };
}
