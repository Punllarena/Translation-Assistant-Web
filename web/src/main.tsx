import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";
import { ApiError } from "./api/client";
import App from "./App";
import "./styles.css";

// An expired session surfaces as a 401 on whatever request comes next. Marking the user
// signed out makes RequireAuth redirect to /login?next=<this page>.
function signedOutOn401(error: Error) {
  if (error instanceof ApiError && error.status === 401) queryClient.setQueryData(["me"], null);
}

const queryClient: QueryClient = new QueryClient({
  queryCache: new QueryCache({ onError: signedOutOn401 }),
  mutationCache: new MutationCache({ onError: signedOutOn401 }),
  defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
