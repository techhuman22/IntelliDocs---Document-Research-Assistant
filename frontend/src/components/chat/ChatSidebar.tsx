"use client";

import { Plus, MessageSquare, Trash2 } from "lucide-react";
import { cn, formatRelativeTime, truncate } from "@/lib/utils";
import type { ChatSession } from "@/types/chat";

interface ChatSidebarProps {
  sessions: ChatSession[];
  activeSessionId: string | null;
  onSelect: (sessionId: string) => void;
  onNew: () => void;
  onDelete: (sessionId: string) => void;
  isLoading?: boolean;
}

export function ChatSidebar({
  sessions,
  activeSessionId,
  onSelect,
  onNew,
  onDelete,
  isLoading,
}: ChatSidebarProps) {
  return (
    <aside className="flex w-64 flex-shrink-0 flex-col border-r border-border bg-card">
      {/* New chat button */}
      <div className="p-3">
        <button
          onClick={onNew}
          className="flex w-full items-center justify-center gap-2 rounded-xl border border-primary/30 bg-primary/5 px-4 py-2.5 text-sm font-medium text-primary hover:bg-primary/10 transition-colors"
        >
          <Plus className="h-4 w-4" />
          New Chat
        </button>
      </div>

      {/* Session list */}
      <div className="flex-1 overflow-y-auto p-2">
        {isLoading ? (
          <div className="flex flex-col gap-2 p-2">
            {[...Array(5)].map((_, i) => (
              <div
                key={i}
                className="h-14 rounded-lg bg-muted animate-pulse"
              />
            ))}
          </div>
        ) : sessions.length === 0 ? (
          <div className="flex flex-col items-center gap-3 p-6 text-center">
            <MessageSquare className="h-8 w-8 text-muted-foreground/30" />
            <p className="text-sm text-muted-foreground">No conversations yet</p>
          </div>
        ) : (
          <ul className="space-y-1">
            {sessions.map((session) => (
              <li key={session.id}>
                <div
                  onClick={() => onSelect(session.id)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => e.key === "Enter" && onSelect(session.id)}
                  className={cn(
                    "group flex w-full cursor-pointer items-center gap-3 rounded-lg px-3 py-2.5 text-left transition-colors",
                    session.id === activeSessionId
                      ? "bg-primary/10 text-primary"
                      : "hover:bg-accent"
                  )}
                >
                  <MessageSquare className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">
                      {session.title ?? "Untitled conversation"}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {session.message_count} messages ·{" "}
                      {formatRelativeTime(session.last_active_at)}
                    </p>
                  </div>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onDelete(session.id);
                    }}
                    className="hidden rounded-md p-1 text-muted-foreground hover:text-red-500 group-hover:flex transition-colors"
                    title="Delete"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </aside>
  );
}
