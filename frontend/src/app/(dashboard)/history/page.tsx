"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import {
  MessageSquare,
  Search,
  Trash2,
  ArrowRight,
  Clock,
} from "lucide-react";
import toast from "react-hot-toast";
import { chatApi } from "@/lib/api/chat";
import { queryKeys } from "@/lib/queryClient";
import { formatRelativeTime, formatDateTime } from "@/lib/utils";
import { PageLoader } from "@/components/common/LoadingSpinner";

export default function HistoryPage() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: queryKeys.sessions.list(),
    queryFn: () => chatApi.listSessions({ limit: 100 }),
  });

  const archiveMutation = useMutation({
    mutationFn: chatApi.archiveSession,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.sessions.list() });
      toast.success("Session deleted");
    },
    onError: () => toast.error("Failed to delete session"),
  });

  const sessions = (data?.sessions ?? []).filter((s) =>
    search
      ? (s.title ?? "Untitled conversation")
          .toLowerCase()
          .includes(search.toLowerCase())
      : true
  );

  return (
    <div className="flex flex-col gap-6 p-6 lg:p-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight">History</h1>
        <p className="text-sm text-muted-foreground mt-0.5">
          All your previous research conversations
        </p>
      </div>

      {/* Search */}
      <div className="relative max-w-sm">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search sessions…"
          className="w-full rounded-xl border border-input bg-background py-2.5 pl-9 pr-4 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-colors"
        />
      </div>

      {isLoading ? (
        <PageLoader label="Loading history…" />
      ) : sessions.length === 0 ? (
        <div className="flex flex-col items-center gap-4 py-16 text-center">
          <MessageSquare className="h-12 w-12 text-muted-foreground/30" />
          <div>
            <p className="font-medium">
              {search ? "No sessions match your search" : "No conversations yet"}
            </p>
            <p className="text-sm text-muted-foreground mt-1">
              {search ? "Try a different term" : "Start chatting to see your history here"}
            </p>
          </div>
          {!search && (
            <Link
              href="/chat"
              className="mt-2 rounded-xl bg-primary px-5 py-2.5 text-sm font-semibold text-white hover:bg-primary/90 transition-colors"
            >
              Start a conversation
            </Link>
          )}
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {sessions.map((session) => (
            <div
              key={session.id}
              className="card-base group flex items-center gap-4 hover:border-primary/30 transition-colors"
            >
              {/* Icon */}
              <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl bg-violet-500/10">
                <MessageSquare className="h-5 w-5 text-violet-500" />
              </div>

              {/* Info */}
              <div className="flex-1 min-w-0">
                <p className="font-medium truncate">
                  {session.title ?? "Untitled conversation"}
                </p>
                <div className="flex items-center gap-3 mt-0.5 text-xs text-muted-foreground">
                  <span className="flex items-center gap-1">
                    <MessageSquare className="h-3 w-3" />
                    {session.message_count} messages
                  </span>
                  <span className="flex items-center gap-1">
                    <Clock className="h-3 w-3" />
                    {formatRelativeTime(session.last_active_at)}
                  </span>
                  <span className="hidden sm:block">
                    {formatDateTime(session.created_at)}
                  </span>
                </div>
              </div>

              {/* Actions */}
              <div className="flex items-center gap-2 flex-shrink-0">
                <button
                  onClick={() => archiveMutation.mutate(session.id)}
                  disabled={archiveMutation.isPending && archiveMutation.variables === session.id}
                  className="hidden rounded-lg p-2 text-muted-foreground hover:bg-red-500/10 hover:text-red-500 transition-colors group-hover:flex"
                  title="Delete session"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
                <Link
                  href={`/chat?session=${session.id}`}
                  className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs font-medium hover:bg-accent transition-colors"
                >
                  Continue
                  <ArrowRight className="h-3.5 w-3.5" />
                </Link>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
