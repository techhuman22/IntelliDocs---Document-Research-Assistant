import { QueryClient } from "@tanstack/react-query";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Data is considered fresh for 60 seconds — avoids redundant refetches
      staleTime: 60 * 1000,
      // Keep unused data in cache for 5 minutes
      gcTime: 5 * 60 * 1000,
      // Retry once on failure (not three times — LLM calls are expensive)
      retry: 1,
      // Don't refetch when user returns to tab (agents may still be running)
      refetchOnWindowFocus: false,
    },
    mutations: {
      retry: 0,
    },
  },
});

// Query key factory — centralised so key changes are caught by TypeScript
export const queryKeys = {
  user: ["user"] as const,
  documents: {
    all: ["documents"] as const,
    list: (params?: object) => ["documents", "list", params] as const,
    detail: (id: string) => ["documents", id] as const,
    stats: ["documents", "stats"] as const,
  },
  sessions: {
    all: ["sessions"] as const,
    list: (params?: object) => ["sessions", "list", params] as const,
    detail: (id: string) => ["sessions", id] as const,
    messages: (id: string) => ["sessions", id, "messages"] as const,
  },
};
