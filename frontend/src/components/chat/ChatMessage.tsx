"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Bot, User, ChevronDown, ChevronUp, BookOpen } from "lucide-react";
import { useState } from "react";
import { cn, formatLatency, getIntentLabel, getIntentIcon } from "@/lib/utils";
import type { ClientMessage, Citation, AgentTraceEntry } from "@/types/chat";
import { AgentActivityPanel, traceToSteps } from "./AgentActivityPanel";
import { ThinkingDots } from "@/components/common/LoadingSpinner";

interface ChatMessageProps {
  message: ClientMessage;
  isStreaming?: boolean;
}

function CitationChip({ citation }: { citation: Citation }) {
  return (
    <div className="flex items-center gap-1.5 rounded-lg border border-border bg-muted/50 px-2.5 py-1.5 text-xs">
      <BookOpen className="h-3 w-3 text-primary flex-shrink-0" />
      <span className="font-medium truncate max-w-[150px]" title={citation.original_filename}>
        {citation.original_filename}
      </span>
      {citation.page_number && (
        <span className="text-muted-foreground">p.{citation.page_number}</span>
      )}
      <span className="rounded-full bg-primary/10 px-1.5 py-0.5 text-primary font-mono">
        {Math.round(citation.similarity_score * 100)}%
      </span>
    </div>
  );
}

export function ChatMessage({ message, isStreaming }: ChatMessageProps) {
  const isUser = message.role === "user";
  const [showTrace, setShowTrace] = useState(false);

  return (
    <div
      className={cn(
        "flex gap-3 animate-slide-in",
        isUser ? "flex-row-reverse" : "flex-row"
      )}
    >
      {/* Avatar */}
      <div
        className={cn(
          "flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full",
          isUser ? "bg-primary" : "bg-muted"
        )}
      >
        {isUser ? (
          <User className="h-4 w-4 text-white" />
        ) : (
          <Bot className="h-4 w-4 text-foreground" />
        )}
      </div>

      {/* Bubble */}
      <div className={cn("flex flex-col gap-2", isUser ? "items-end" : "items-start", "max-w-[85%]")}>
        {isUser ? (
          <div className="chat-bubble-user">{message.content}</div>
        ) : (
          <>
            {/* Intent badge */}
            {message.intent && message.intent !== "unknown" && (
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <span>{getIntentIcon(message.intent)}</span>
                <span>{getIntentLabel(message.intent)}</span>
              </div>
            )}

            {/* Content bubble */}
            <div className="chat-bubble-assistant">
              {isStreaming && !message.content ? (
                <ThinkingDots />
              ) : (
                <div className="prose prose-sm dark:prose-invert max-w-none text-foreground">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {message.content}
                  </ReactMarkdown>
                </div>
              )}
            </div>

            {/* Citations */}
            {message.citations && message.citations.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {message.citations.map((c, i) => (
                  <CitationChip key={i} citation={c} />
                ))}
              </div>
            )}

            {/* Meta row: latency + trace toggle */}
            {(message.latency_ms || message.agent_trace?.length) && (
              <div className="flex items-center gap-3">
                {message.latency_ms && (
                  <span className="text-xs text-muted-foreground">
                    {formatLatency(message.latency_ms)}
                  </span>
                )}
                {message.agent_trace && message.agent_trace.length > 0 && (
                  <button
                    onClick={() => setShowTrace(!showTrace)}
                    className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
                  >
                    {showTrace ? (
                      <ChevronUp className="h-3 w-3" />
                    ) : (
                      <ChevronDown className="h-3 w-3" />
                    )}
                    Agent trace
                  </button>
                )}
              </div>
            )}

            {/* Agent trace panel */}
            {showTrace && message.agent_trace && (
              <AgentActivityPanel
                steps={traceToSteps(message.agent_trace)}
                isStreaming={false}
                className="w-full"
              />
            )}
          </>
        )}
      </div>
    </div>
  );
}
