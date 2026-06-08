"use client";

import { useState, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Search, RefreshCw, HardDrive } from "lucide-react";
import toast from "react-hot-toast";
import { UploadArea } from "@/components/documents/UploadArea";
import { DocumentCard } from "@/components/documents/DocumentCard";
import { PageLoader } from "@/components/common/LoadingSpinner";
import { documentsApi } from "@/lib/api/documents";
import { queryKeys } from "@/lib/queryClient";
import { formatBytes } from "@/lib/utils";
import type { Document } from "@/types/document";

export default function DocumentsPage() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");

  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: queryKeys.documents.list({ search }),
    queryFn: () => documentsApi.list({ search: search || undefined }),
    // Auto-poll every 3s while any document is still processing
    refetchInterval: (query) => {
      const items = (query.state.data as any)?.items ?? [];
      const hasActive = items.some((d: any) => d.status === "pending" || d.status === "processing");
      return hasActive ? 3000 : false;
    },
  });

  const { data: stats } = useQuery({
    queryKey: queryKeys.documents.stats,
    queryFn: documentsApi.getStorageStats,
  });

  const deleteMutation = useMutation({
    mutationFn: documentsApi.delete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.documents.all });
      toast.success("Document deleted");
    },
    onError: () => toast.error("Failed to delete document"),
  });

  const processMutation = useMutation({
    mutationFn: documentsApi.triggerProcessing,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.documents.all });
      toast.success("Processing started");
    },
    onError: () => toast.error("Failed to start processing"),
  });

  const handleUpload = useCallback(
    async (file: File, onProgress: (p: number) => void) => {
      await documentsApi.upload(file, onProgress);
      queryClient.invalidateQueries({ queryKey: queryKeys.documents.all });
    },
    [queryClient]
  );

  const documents: Document[] = data?.items ?? [];
  const filtered = search
    ? documents.filter((d) =>
        d.original_filename.toLowerCase().includes(search.toLowerCase())
      )
    : documents;

  return (
    <div className="flex flex-col gap-6 p-6 lg:p-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Documents</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Upload and manage your research documents
          </p>
        </div>
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <HardDrive className="h-4 w-4" />
          {stats?.total_mb ?? 0} MB used
        </div>
      </div>

      {/* Upload area */}
      <UploadArea onUpload={handleUpload} />

      {/* Search + refresh bar */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search documents…"
            className="w-full rounded-xl border border-input bg-background py-2.5 pl-9 pr-4 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-colors"
          />
        </div>
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="flex items-center gap-1.5 rounded-xl border border-border px-3 py-2.5 text-sm hover:bg-accent transition-colors disabled:opacity-60"
          title="Refresh"
        >
          <RefreshCw className={`h-4 w-4 ${isFetching ? "animate-spin" : ""}`} />
        </button>
      </div>

      {/* Document list */}
      {isLoading ? (
        <PageLoader label="Loading documents…" />
      ) : filtered.length === 0 ? (
        <div className="flex flex-col items-center gap-3 py-16 text-center">
          <Search className="h-10 w-10 text-muted-foreground/30" />
          <p className="font-medium">
            {search ? "No documents match your search" : "No documents yet"}
          </p>
          <p className="text-sm text-muted-foreground">
            {search
              ? "Try a different search term"
              : "Upload your first document above"}
          </p>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((doc) => (
            <DocumentCard
              key={doc.id}
              document={doc}
              onDelete={() => deleteMutation.mutate(doc.id)}
              onProcess={() => processMutation.mutate(doc.id)}
              isDeleting={deleteMutation.isPending && deleteMutation.variables === doc.id}
              isProcessing={processMutation.isPending && processMutation.variables === doc.id}
            />
          ))}
        </div>
      )}
    </div>
  );
}
