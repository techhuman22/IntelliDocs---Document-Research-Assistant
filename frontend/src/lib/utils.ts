import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import { formatDistanceToNow, format } from "date-fns";

// shadcn/ui class merger — use this everywhere instead of raw clsx
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// ── Formatting ────────────────────────────────────────────────────────────────

export function formatBytes(bytes: number, decimals = 2): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(decimals))} ${sizes[i]}`;
}

export function formatRelativeTime(dateString: string): string {
  return formatDistanceToNow(new Date(dateString), { addSuffix: true });
}

export function formatDateTime(dateString: string): string {
  return format(new Date(dateString), "MMM d, yyyy 'at' h:mm a");
}

export function formatLatency(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

// ── Document helpers ──────────────────────────────────────────────────────────

export function getFileIcon(fileType: string): string {
  switch (fileType.toLowerCase()) {
    case "pdf": return "📄";
    case "docx": case "doc": return "📝";
    case "txt": return "📃";
    default: return "📎";
  }
}

export function getStatusColor(status: string): string {
  switch (status) {
    case "ready": return "text-emerald-500";
    case "processing": return "text-amber-500";
    case "pending": return "text-slate-400";
    case "failed": return "text-red-500";
    default: return "text-slate-400";
  }
}

export function getStatusBadgeClass(status: string): string {
  switch (status) {
    case "ready":
      return "bg-emerald-500/10 text-emerald-500 border-emerald-500/20";
    case "processing":
      return "bg-amber-500/10 text-amber-500 border-amber-500/20";
    case "pending":
      return "bg-slate-500/10 text-slate-400 border-slate-500/20";
    case "failed":
      return "bg-red-500/10 text-red-500 border-red-500/20";
    default:
      return "bg-slate-500/10 text-slate-400 border-slate-500/20";
  }
}

// ── Intent helpers ────────────────────────────────────────────────────────────

export function getIntentIcon(intent: string): string {
  switch (intent) {
    case "qa": return "💬";
    case "summary": return "📋";
    case "quiz": return "🎯";
    default: return "🤖";
  }
}

export function getIntentLabel(intent: string): string {
  switch (intent) {
    case "qa": return "Answer";
    case "summary": return "Summary";
    case "quiz": return "Quiz";
    default: return "Response";
  }
}

// ── Agent helpers ─────────────────────────────────────────────────────────────

export function getAgentIcon(agentName: string): string {
  switch (agentName) {
    case "router": return "🧭";
    case "retrieval": return "🔍";
    case "summary": return "📋";
    case "quiz": return "🎯";
    case "final_response": return "✨";
    default: return "🤖";
  }
}

export function getAgentLabel(agentName: string): string {
  switch (agentName) {
    case "router": return "Analyzing intent";
    case "retrieval": return "Searching documents";
    case "summary": return "Generating summary";
    case "quiz": return "Creating questions";
    case "final_response": return "Composing response";
    default: return agentName;
  }
}

// ── String helpers ────────────────────────────────────────────────────────────

export function truncate(str: string, length: number): string {
  if (str.length <= length) return str;
  return str.slice(0, length) + "…";
}

export function generateId(): string {
  return Math.random().toString(36).slice(2, 11);
}
