import apiClient from "./axios";
import type {
  ChatResponse,
  ChatSession,
  MessageHistoryResponse,
  SessionListResponse,
  StreamEvent,
} from "@/types/chat";

export const chatApi = {
  // ── Chat ───────────────────────────────────────────────────────────────────

  send: async (data: {
    query: string;
    session_id?: string;
    document_ids?: string[];
  }): Promise<ChatResponse> => {
    const response = await apiClient.post<ChatResponse>("/api/v1/chat", data);
    return response.data;
  },

  /**
   * Streaming chat — yields StreamEvent objects via an async generator.
   *
   * Uses the Fetch API (not Axios) because Axios does not support
   * ReadableStream response bodies. We read the SSE lines manually.
   *
   * Usage:
   *   for await (const event of chatApi.stream({query: "..."})) {
   *     if (event.event_type === "final") { ... }
   *   }
   */
  stream: async function* (data: {
    query: string;
    session_id?: string;
    document_ids?: string[];
  }): AsyncGenerator<StreamEvent> {
    const baseUrl =
      process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    const token =
      typeof window !== "undefined"
        ? localStorage.getItem("access_token")
        : null;

    const response = await fetch(`${baseUrl}/api/v1/chat/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(data),
    });

    if (!response.ok || !response.body) {
      throw new Error(`Stream failed: ${response.status} ${response.statusText}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // SSE lines are separated by \n\n; each line starts with "data: "
        const lines = buffer.split("\n\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          const trimmed = line.trim();
          if (trimmed.startsWith("data: ")) {
            const jsonStr = trimmed.slice(6);
            try {
              const event: StreamEvent = JSON.parse(jsonStr);
              yield event;
            } catch {
              // malformed line — skip
            }
          }
        }
      }
    } finally {
      reader.releaseLock();
    }
  },

  // ── Sessions ───────────────────────────────────────────────────────────────

  createSession: async (data: {
    title?: string;
    document_ids?: string[];
    session_type?: string;
  }): Promise<ChatSession> => {
    const response = await apiClient.post<ChatSession>("/api/v1/sessions", data);
    return response.data;
  },

  listSessions: async (params?: {
    page?: number;
    limit?: number;
    include_archived?: boolean;
  }): Promise<SessionListResponse> => {
    const response = await apiClient.get<SessionListResponse>(
      "/api/v1/sessions",
      { params }
    );
    return response.data;
  },

  getSession: async (sessionId: string): Promise<ChatSession> => {
    const response = await apiClient.get<ChatSession>(
      `/api/v1/sessions/${sessionId}`
    );
    return response.data;
  },

  archiveSession: async (sessionId: string): Promise<void> => {
    await apiClient.delete(`/api/v1/sessions/${sessionId}`);
  },

  getMessages: async (
    sessionId: string,
    params?: { page?: number; limit?: number }
  ): Promise<MessageHistoryResponse> => {
    const response = await apiClient.get<MessageHistoryResponse>(
      `/api/v1/sessions/${sessionId}/messages`,
      { params }
    );
    return response.data;
  },
};
