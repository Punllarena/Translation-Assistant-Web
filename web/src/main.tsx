import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router";
import { router } from "./App";
import { signedOutOn401 } from "./auth/session";
import "./fonts";
import { startsJob } from "./jobs/follow";
import { ACTIVE_JOBS_KEY } from "./jobs/RunningJobs";
import "./styles/index.css";
import { startTheme } from "./theme/theme";

const onError = (error: Error) => signedOutOn401(queryClient, error);

const queryClient: QueryClient = new QueryClient({
  queryCache: new QueryCache({ onError }),
  mutationCache: new MutationCache({
    onError,
    // Any mutation that starts a job shows up in the header's running-jobs button at once.
    onSuccess: (data) => { if (startsJob(data)) void queryClient.invalidateQueries({ queryKey: ACTIVE_JOBS_KEY }); },
  }),
  defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
});

startTheme();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
);
