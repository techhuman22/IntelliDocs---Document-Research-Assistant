"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import {
  FileText,
  MessageSquare,
  HardDrive,
  Zap,
  ArrowRight,
  Plus,
} from "lucide-react";
import { DashboardCard } from "@/components/dashboard/DashboardCard";
import { useAuthContext } from "@/contexts/AuthContext";
import { documentsApi } from "@/lib/api/documents";
import { chatApi } from "@/lib/api/chat";
import { queryKeys } from "@/lib/queryClient";
import { formatBytes, formatRelativeTime } from "@/lib/utils";
import { PageLoader } from "@/components/common/LoadingSpinner";
import type { Metadata } from "next";

export default function DashboardPage() {
  const { user } = useAuthContext();

  const { data: docsData, isLoading: docsLoading } = useQuery({
    queryKey: queryKeys.documents.stats,
    queryFn: documentsApi.getStorageStats,
  });

  const { data: sessionsData, isLoading: sessionsLoading } = useQuery({
    queryKey: queryKeys.sessions.list(),
    queryFn: () => chatApi.listSessions({ limit: 5 }),
  });

  const { data: recentDocs, isLoading: recentLoading } = useQuery({
    queryKey: queryKeys.documents.list({ limit: 5 }),
    queryFn: () => documentsApi.list({ limit: 5 }),
  });

  const isLoading = docsLoading || sessionsLoading || recentLoading;

  if (isLoading) return <PageLoader label="Loading dashboard…" />;

  const greeting = () => {
    const h = new Date().getHours();
    if (h < 12) return "Good morning";
    if (h < 17) return "Good afternoon";
    return "Good evening";
  };

  return (
    <div className="flex flex-col gap-8 p-6 lg:p-8">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">
            {greeting()},{" "}
            <span className="gradient-text">
              {user?.full_name?.split(" ")[0] ?? "there"}
            </span>{" "}
            👋
          </h1>
          <p className="text-muted-foreground mt-1">
            Here&apos;s what&apos;s happening with your research.
          </p>
        </div>
        <Link
          href="/chat"
          className="flex items-center gap-2 rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-white hover:bg-primary/90 transition-colors shadow-lg shadow-primary/20"
        >
          <Plus className="h-4 w-4" />
          New Chat
        </Link>
      </div>

      {/* Stats cards */}
      <div className="grid gap-4 sm:grid-cols-2">
        <DashboardCard
          title="Total Documents"
          value={docsData?.document_count ?? 0}
          subtitle="uploaded files"
          icon={FileText}
          iconColor="text-indigo-500"
        />
        <DashboardCard
          title="Total Chats"
          value={sessionsData?.total ?? 0}
          subtitle="conversation sessions"
          icon={MessageSquare}
          iconColor="text-violet-500"
        />
      </div>

      {/* Two-column: recent docs + recent chats */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Recent documents */}
        <div className="card-base flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold">Recent Documents</h2>
            <Link
              href="/documents"
              className="flex items-center gap-1 text-sm text-primary hover:underline"
            >
              View all
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>

          {(recentDocs?.items?.length ?? 0) === 0 ? (
            <div className="flex flex-col items-center gap-3 py-8 text-center">
              <FileText className="h-10 w-10 text-muted-foreground/30" />
              <p className="text-sm text-muted-foreground">No documents yet</p>
              <Link
                href="/documents"
                className="text-sm text-primary hover:underline"
              >
                Upload your first document
              </Link>
            </div>
          ) : (
            <ul className="flex flex-col gap-2">
              {recentDocs?.items?.map((doc) => (
                <li
                  key={doc.id}
                  className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-accent transition-colors"
                >
                  <FileText className="h-4 w-4 flex-shrink-0 text-primary" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">
                      {doc.original_filename}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {doc.status} · {formatRelativeTime(doc.created_at)}
                    </p>
                  </div>
                  <span
                    className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                      doc.status === "ready"
                        ? "bg-emerald-500/10 text-emerald-500"
                        : doc.status === "failed"
                        ? "bg-red-500/10 text-red-500"
                        : "bg-amber-500/10 text-amber-500"
                    }`}
                  >
                    {doc.status}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Recent chats */}
        <div className="card-base flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold">Recent Chats</h2>
            <Link
              href="/history"
              className="flex items-center gap-1 text-sm text-primary hover:underline"
            >
              View all
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>

          {(sessionsData?.sessions?.length ?? 0) === 0 ? (
            <div className="flex flex-col items-center gap-3 py-8 text-center">
              <MessageSquare className="h-10 w-10 text-muted-foreground/30" />
              <p className="text-sm text-muted-foreground">No chats yet</p>
              <Link href="/chat" className="text-sm text-primary hover:underline">
                Start your first conversation
              </Link>
            </div>
          ) : (
            <ul className="flex flex-col gap-2">
              {sessionsData?.sessions?.map((session) => (
                <li key={session.id}>
                  <Link
                    href={`/chat?session=${session.id}`}
                    className="flex items-center gap-3 rounded-lg px-3 py-2 hover:bg-accent transition-colors"
                  >
                    <MessageSquare className="h-4 w-4 flex-shrink-0 text-violet-500" />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">
                        {session.title ?? "Untitled conversation"}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {session.message_count} messages ·{" "}
                        {formatRelativeTime(session.last_active_at)}
                      </p>
                    </div>
                    <ArrowRight className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {/* Quick actions */}
      <div className="card-base">
        <h2 className="mb-4 font-semibold">Quick actions</h2>
        <div className="grid gap-3 sm:grid-cols-3">
          {[
            {
              href: "/documents",
              icon: FileText,
              label: "Upload document",
              desc: "PDF, DOCX, TXT",
              color: "text-indigo-500",
              bg: "bg-indigo-500/10",
            },
            {
              href: "/chat",
              icon: MessageSquare,
              label: "Start new chat",
              desc: "Ask about documents",
              color: "text-violet-500",
              bg: "bg-violet-500/10",
            },
            {
              href: "/history",
              icon: Zap,
              label: "View history",
              desc: "Past conversations",
              color: "text-amber-500",
              bg: "bg-amber-500/10",
            },
          ].map((action) => (
            <Link
              key={action.href}
              href={action.href}
              className="flex items-center gap-3 rounded-xl border border-border p-4 hover:border-primary/30 hover:bg-accent transition-all group"
            >
              <div className={`flex h-10 w-10 items-center justify-center rounded-xl ${action.bg}`}>
                <action.icon className={`h-5 w-5 ${action.color}`} />
              </div>
              <div>
                <p className="font-medium text-sm">{action.label}</p>
                <p className="text-xs text-muted-foreground">{action.desc}</p>
              </div>
              <ArrowRight className="ml-auto h-4 w-4 text-muted-foreground group-hover:text-foreground transition-colors" />
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
