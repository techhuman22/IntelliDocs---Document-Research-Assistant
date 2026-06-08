"use client";

import { CheckCircle2, Circle, Loader2 } from "lucide-react";
import { cn, formatLatency, getAgentIcon, getAgentLabel } from "@/lib/utils";
import type { AgentTraceEntry } from "@/types/chat";

interface AgentStep {
  name: string;
  status: "waiting" | "running" | "success" | "error" | "skipped";
  latency_ms?: number;
}

/**
 * Convert backend AgentTraceEntry[] to AgentStep[] for display.
 * Used when rendering a completed message's trace in history.
 */
export function traceToSteps(trace: AgentTraceEntry[]): AgentStep[] {
  return trace.map((t) => ({
    name: t.agent_name,
    status: t.status === "success"
      ? "success"
      : t.status === "error"
      ? "error"
      : "skipped",
    latency_ms: t.latency_ms ?? undefined,
  }));
}

interface AgentActivityPanelProps {
  /** Pass either pre-converted steps or a raw trace — one of the two. */
  steps?: AgentStep[];
  trace?: AgentTraceEntry[];
  isStreaming: boolean;
  className?: string;
}

/**
 * Shows live agent execution progress while the pipeline is running.
 * Used inside the chat interface while isStreaming=true.
 *
 * Steps are determined by the stream events from the backend:
 *   agent_end → mark that step complete
 */
export function AgentActivityPanel({
  steps: stepsProp,
  trace,
  isStreaming,
  className,
}: AgentActivityPanelProps) {
  // Accept either pre-built steps or a raw trace
  const steps: AgentStep[] = stepsProp ?? (trace ? traceToSteps(trace) : []);
  if (steps.length === 0 && !isStreaming) return null;

  return (
    <div
      className={cn(
        "rounded-xl border border-border bg-card/50 px-4 py-3",
        className
      )}
    >
      <p className="mb-3 text-xs font-semibold uppercase tracking-widest text-muted-foreground">
        Agent Pipeline
      </p>
      <div className="flex flex-col gap-2">
        {steps.map((step, idx) => (
          <div key={step.name + idx} className="flex items-center gap-3">
            {/* Status icon */}
            <div className="flex-shrink-0">
              {step.status === "running" ? (
                <Loader2 className="h-4 w-4 animate-spin text-primary" />
              ) : step.status === "success" ? (
                <CheckCircle2 className="h-4 w-4 text-emerald-500" />
              ) : step.status === "error" ? (
                <Circle className="h-4 w-4 text-red-500 fill-red-500" />
              ) : step.status === "skipped" ? (
                <Circle className="h-4 w-4 text-muted-foreground/30" />
              ) : (
                <Circle className="h-4 w-4 text-muted-foreground/30" />
              )}
            </div>

            {/* Label */}
            <div className="flex flex-1 items-center justify-between gap-2 min-w-0">
              <span
                className={cn(
                  "text-sm",
                  step.status === "running"
                    ? "text-foreground font-medium"
                    : step.status === "success"
                    ? "text-muted-foreground"
                    : "text-muted-foreground/50"
                )}
              >
                {getAgentIcon(step.name)} {getAgentLabel(step.name)}
              </span>
              {step.latency_ms != null && (
                <span className="text-xs text-muted-foreground flex-shrink-0">
                  {formatLatency(step.latency_ms)}
                </span>
              )}
            </div>
          </div>
        ))}

        {/* Animated "Thinking..." row when streaming but no more events yet */}
        {isStreaming && steps.every((s) => s.status !== "running") && (
          <div className="flex items-center gap-3">
            <Loader2 className="h-4 w-4 animate-spin text-primary flex-shrink-0" />
            <span className="text-sm text-foreground font-medium animate-pulse">
              Processing…
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
