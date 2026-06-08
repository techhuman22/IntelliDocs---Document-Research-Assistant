"use client";

import {
  useState,
  useRef,
  useEffect,
  useCallback,
  Suspense,
} from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import toast from "react-hot-toast";
import { ChatSidebar } from "@/components/chat/ChatSidebar";
import { ChatMessage } from "@/components/chat/ChatMessage";
import { ChatInput } from "@/components/chat/ChatInput";
import { AgentActivityPanel } from "@/components/chat/AgentActivityPanel";
import { ThinkingDots } from "@/components/common/LoadingSpinner";
import { chatApi } from "@/lib/api/chat";
import { queryKeys } from "@/lib/queryClient";
import { generateId } from "@/lib/utils";
import type {
  ClientMessage,
  AgentTraceEntry,
  StreamEvent,
  ChatSession,
} from "@/types/chat";
import { BrainCircuit, PanelRightClose, PanelRightOpen, FileText, ChevronDown, X } from "lucide-react";
import { documentsApi } from "@/lib/api/documents";

function ChatPageInner() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const queryClient = useQueryClient();

  const [activeSessionId, setActiveSessionId] = useState<string | null>(
    searchParams.get("session")
  );
  const [messages, setMessages] = useState<ClientMessage[]>([]);
  const [streamingText, setStreamingText] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [agentTrace, setAgentTrace] = useState<AgentTraceEntry[]>([]);
  const [showAgentPanel, setShowAgentPanel] = useState(true);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [selectedDocIds, setSelectedDocIds] = useState<string[]>([]);
  const [showDocPicker, setShowDocPicker] = useState(false);
  const docPickerRef = useRef<HTMLDivElement>(null);

  // Close doc picker on outside click
  useEffect(() => {
    if (!showDocPicker) return;
    const handler = (e: MouseEvent) => {
      if (docPickerRef.current && !docPickerRef.current.contains(e.target as Node)) {
        setShowDocPicker(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [showDocPicker]);

  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const streamGenRef = useRef<AsyncGenerator<StreamEvent> | null>(null);

  // Sessions list
  const { data: sessionsData, isLoading: sessionsLoading } = useQuery({
    queryKey: queryKeys.sessions.list(),
    queryFn: () => chatApi.listSessions({ limit: 50 }),
  });

  // All ready documents for the doc picker
  const { data: docsData } = useQuery({
    queryKey: queryKeys.documents.list({ status: "ready" }),
    queryFn: () => documentsApi.list({ limit: 100 }),
  });

  // Message history for active session
  const { data: historyData } = useQuery({
    queryKey: activeSessionId
      ? queryKeys.sessions.messages(activeSessionId)
      : ["noop"],
    queryFn: () => chatApi.getMessages(activeSessionId!),
    enabled: !!activeSessionId,
  });

  // Populate messages from history
  useEffect(() => {
    if (!historyData) return;
    const mapped: ClientMessage[] = historyData.messages.map((m) => ({
      id: m.id,
      role: m.role as "user" | "assistant",
      content: m.content,
      citations: m.citations ?? [],
      agent_trace: m.agent_trace ?? [],
      created_at: m.created_at,
    }));
    setMessages(mapped);
  }, [historyData]);

  // Scroll to bottom on new message
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingText]);

  // Create session mutation
  const createSessionMutation = useMutation({
    mutationFn: chatApi.createSession,
    onSuccess: (session: ChatSession) => {
      setActiveSessionId(session.id);
      router.replace(`/chat?session=${session.id}`, { scroll: false });
      queryClient.invalidateQueries({ queryKey: queryKeys.sessions.list() });
    },
  });

  // Archive / delete session
  const archiveMutation = useMutation({
    mutationFn: chatApi.archiveSession,
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.sessions.list() });
      if (id === activeSessionId) {
        setActiveSessionId(null);
        setMessages([]);
        router.replace("/chat", { scroll: false });
      }
      toast.success("Session archived");
    },
  });

  const handleNewChat = useCallback(async () => {
    stopStreaming();
    setMessages([]);
    setStreamingText("");
    setAgentTrace([]);
    setActiveSessionId(null);
    router.replace("/chat", { scroll: false });
  }, [router]);

  const handleSelectSession = useCallback(
    (id: string) => {
      if (id === activeSessionId) return;
      stopStreaming();
      setMessages([]);
      setStreamingText("");
      setAgentTrace([]);
      setActiveSessionId(id);
      router.replace(`/chat?session=${id}`, { scroll: false });
    },
    [activeSessionId, router]
  );

  const stopStreaming = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setIsStreaming(false);
  }, []);

  const handleSend = useCallback(
    async (text: string) => {
      if (!text.trim() || isStreaming) return;

      // Optimistic user message
      const userMsg: ClientMessage = {
        id: generateId(),
        role: "user",
        content: text,
        citations: [],
        agent_trace: [],
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, userMsg]);
      setStreamingText("");
      setAgentTrace([]);
      setIsStreaming(true);

      const abort = new AbortController();
      abortRef.current = abort;

      try {
        // Create session on first message
        let sessionId = activeSessionId;
        if (!sessionId) {
          const session = await chatApi.createSession({ title: text.slice(0, 60) });
          sessionId = session.id;
          setActiveSessionId(sessionId);
          router.replace(`/chat?session=${sessionId}`, { scroll: false });
          queryClient.invalidateQueries({ queryKey: queryKeys.sessions.list() });
        }

        const gen = chatApi.stream(
          {
            session_id: sessionId,
            query: text,
            document_ids: selectedDocIds.length > 0 ? selectedDocIds : undefined,
          },
          abort.signal
        );
        streamGenRef.current = gen;

        let fullText = "";
        let finalCitations: ClientMessage["citations"] = [];
        let finalTrace: AgentTraceEntry[] = [];

        for await (const event of gen) {
          if (abort.signal.aborted) break;

          // Backend sends event_type (not type), map to frontend actions:
          // "token"     → append to streaming text
          // "agent_end" → record agent step in trace panel
          // "final"     → full response with citations + trace
          // "error"     → show toast
          if (event.event_type === "token") {
            fullText += (event.data as { token?: string })?.token ?? (event.data as string ?? "");
            setStreamingText(fullText);
          } else if (event.event_type === "agent_end") {
            const step = event.data as { agent?: string; status?: string; latency_ms?: number };
            const traceEntry: AgentTraceEntry = {
              agent_name: step.agent ?? "unknown",
              status: (step.status as AgentTraceEntry["status"]) ?? "success",
              latency_ms: step.latency_ms ?? null,
              token_input: null,
              token_output: null,
            };
            setAgentTrace((prev) => [...prev, traceEntry]);
            finalTrace = [...finalTrace, traceEntry];
          } else if (event.event_type === "final") {
            const payload = event.data as {
              response?: string;
              citations?: ClientMessage["citations"];
              agent_trace?: AgentTraceEntry[];
            };
            // Backend sends full response in "final" (not token-by-token)
            if (payload.response) {
              fullText = payload.response;
              setStreamingText(fullText);
            }
            finalCitations = payload.citations ?? [];
            finalTrace = payload.agent_trace ?? finalTrace;
          } else if (event.event_type === "error") {
            toast.error((event.data as { message?: string })?.message ?? "Stream error");
            break;
          }
        }

        // Commit assistant message
        if (!abort.signal.aborted && fullText) {
          const assistantMsg: ClientMessage = {
            id: generateId(),
            role: "assistant",
            content: fullText,
            citations: finalCitations,
            agent_trace: finalTrace,
            created_at: new Date().toISOString(),
          };
          setMessages((prev) => [...prev, assistantMsg]);
          queryClient.invalidateQueries({
            queryKey: queryKeys.sessions.messages(sessionId!),
          });
          queryClient.invalidateQueries({ queryKey: queryKeys.sessions.list() });
        }
      } catch (err: unknown) {
        if ((err as { name?: string })?.name !== "AbortError") {
          toast.error("Failed to send message");
        }
      } finally {
        setStreamingText("");
        setIsStreaming(false);
        abortRef.current = null;
      }
    },
    [activeSessionId, isStreaming, queryClient, router]
  );

  const allMessages = messages;
  const sessions = sessionsData?.sessions ?? [];

  return (
    <div className="flex h-full min-h-0">
      {/* Chat sidebar — sessions list */}
      {isSidebarOpen && (
        <ChatSidebar
          sessions={sessions}
          activeSessionId={activeSessionId}
          onSelect={handleSelectSession}
          onNew={handleNewChat}
          onDelete={(id) => archiveMutation.mutate(id)}
          isLoading={sessionsLoading}
        />
      )}

      {/* Main chat area */}
      <div className="flex flex-1 flex-col min-w-0">
        {/* Topbar */}
        <div className="flex items-center justify-between border-b border-border px-4 py-2.5 bg-card/50 backdrop-blur-sm">
          <button
            onClick={() => setIsSidebarOpen((v) => !v)}
            className="rounded-lg p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
            title="Toggle sidebar"
          >
            {isSidebarOpen ? (
              <PanelRightOpen className="h-4 w-4" />
            ) : (
              <PanelRightClose className="h-4 w-4" />
            )}
          </button>

          {/* Document selector */}
          <div ref={docPickerRef} className="relative flex items-center gap-2">
            <button
              onClick={() => setShowDocPicker((v) => !v)}
              className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs font-medium hover:bg-accent transition-colors"
            >
              <FileText className="h-3.5 w-3.5 text-primary" />
              {selectedDocIds.length === 0
                ? "All documents"
                : `${selectedDocIds.length} doc${selectedDocIds.length > 1 ? "s" : ""} selected`}
              <ChevronDown className="h-3 w-3 text-muted-foreground" />
            </button>

            {/* Dropdown */}
            {showDocPicker && (
              <div className="absolute top-full left-0 mt-1 z-50 w-72 rounded-xl border border-border bg-popover shadow-xl">
                <div className="p-2 border-b border-border">
                  <p className="text-xs font-semibold text-muted-foreground px-1">
                    Select documents to search
                  </p>
                </div>
                <div className="max-h-52 overflow-y-auto p-1">
                  {(docsData?.items ?? []).length === 0 ? (
                    <p className="text-xs text-muted-foreground p-3 text-center">
                      No documents yet — upload some first
                    </p>
                  ) : (
                    (docsData?.items ?? []).map((doc) => (
                      <label
                        key={doc.id}
                        className="flex items-center gap-2.5 rounded-lg px-3 py-2 hover:bg-accent cursor-pointer"
                      >
                        <input
                          type="checkbox"
                          checked={selectedDocIds.includes(doc.id)}
                          onChange={(e) => {
                            setSelectedDocIds((prev) =>
                              e.target.checked
                                ? [...prev, doc.id]
                                : prev.filter((id) => id !== doc.id)
                            );
                          }}
                          className="accent-primary"
                        />
                        <FileText className="h-3.5 w-3.5 flex-shrink-0 text-primary" />
                        <span className="text-xs truncate flex-1">{doc.original_filename}</span>
                        <span className={`text-[10px] px-1.5 py-0.5 rounded-full flex-shrink-0 ${
                          doc.status === "ready"
                            ? "bg-emerald-500/10 text-emerald-500"
                            : "bg-amber-500/10 text-amber-500"
                        }`}>
                          {doc.status}
                        </span>
                      </label>
                    ))
                  )}
                </div>
                {selectedDocIds.length > 0 && (
                  <div className="p-2 border-t border-border">
                    <button
                      onClick={() => setSelectedDocIds([])}
                      className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground w-full px-1"
                    >
                      <X className="h-3 w-3" />
                      Clear selection (search all)
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>

          <button
            onClick={() => setShowAgentPanel((v) => !v)}
            className="rounded-lg p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
            title="Toggle agent panel"
          >
            <BrainCircuit className="h-4 w-4" />
          </button>
        </div>

        {/* Messages */}
        <div className="flex flex-1 min-h-0">
          <div className="flex flex-1 flex-col overflow-y-auto p-4 gap-4">
            {allMessages.length === 0 && !isStreaming ? (
              <div className="flex flex-1 flex-col items-center justify-center gap-4 text-center py-16">
                <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/10">
                  <BrainCircuit className="h-8 w-8 text-primary" />
                </div>
                <div>
                  <h2 className="text-lg font-semibold">
                    How can I help you today?
                  </h2>
                  <p className="mt-1 text-sm text-muted-foreground max-w-md">
                    Ask me to summarize a document, answer questions, or
                    generate a quiz. Make sure you&apos;ve uploaded and processed
                    your documents first.
                  </p>
                </div>
              </div>
            ) : (
              <>
                {allMessages.map((msg) => (
                  <ChatMessage key={msg.id} message={msg} />
                ))}

                {/* Streaming in-progress bubble */}
                {isStreaming && (
                  <div className="flex flex-col gap-1 max-w-[80%]">
                    <div className="chat-bubble-assistant">
                      {streamingText || <ThinkingDots />}
                      {streamingText && (
                        <span className="inline-block h-4 w-0.5 bg-foreground/60 ml-0.5 animate-pulse" />
                      )}
                    </div>
                  </div>
                )}
              </>
            )}
            <div ref={bottomRef} />
          </div>

          {/* Agent activity panel */}
          {showAgentPanel && (isStreaming || agentTrace.length > 0) && (
            <div className="hidden lg:flex w-72 flex-shrink-0 flex-col border-l border-border">
              <AgentActivityPanel
                trace={agentTrace}
                isStreaming={isStreaming}
              />
            </div>
          )}
        </div>

        {/* Input */}
        <ChatInput
          onSend={handleSend}
          onStop={stopStreaming}
          isStreaming={isStreaming}
          disabled={false}
        />
      </div>
    </div>
  );
}

export default function ChatPage() {
  return (
    <Suspense fallback={<div className="flex flex-1 items-center justify-center text-muted-foreground text-sm">Loading…</div>}>
      <ChatPageInner />
    </Suspense>
  );
}
