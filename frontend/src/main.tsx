import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";

/*
 * Self-hosted Geist. Fontsource ships the woff2 files inside the package, so
 * Vite fingerprints and emits them into the bundle — the app renders correctly
 * with no network at all. Only the weights actually used are imported; each one
 * is a separate file, so importing the full 100-900 range would ship ~9x the
 * bytes for nothing.
 */
import "@fontsource/geist-sans/400.css";
import "@fontsource/geist-sans/500.css";
import "@fontsource/geist-sans/600.css";
import "@fontsource/geist-sans/700.css";
import "@fontsource/geist-mono/400.css";
import "@fontsource/geist-mono/500.css";

import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Transcripts are immutable once written, so refetching on focus is waste.
      refetchOnWindowFocus: false,
      staleTime: 30_000,
      retry: 1,
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);
