"use client";

import { useState } from "react";
import {
  Trash2,
  RefreshCw,
  FileText,
  AlertCircle,
  CheckCircle2,
  Clock,
  Loader2,
} from "lucide-react";
import { cn, formatBytes, formatRelativeTime, getStatusBadgeClass } from "@/lib/utils";
import type { Document } from "@/types/document";

interface DocumentCardProps {
  document: Document;
  onDelete: (id: string) => void;
  onProcess: (id: string) => void;
  isDeleting?: boolean;
  isProcessing?: boolean;
}

const StatusIcon = ({ status }: { status: string }) => {
  switch (status) {
    case "ready":
      return <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />;
    case "processing":
      return <Loader2 className="h-3.5 w-3.5 text-amber-500 animate-spin" />;
    case "failed":
      return <AlertCircle className="h-3.5 w-3.5 text-red-500" />;
    default:
      return <Clock className="h-3.5 w-3.5 text-slate-400" />;
  }
};

export function DocumentCard({
  document,
  onDelete,
  onProcess,
  isDeleting,
  isProcessing,
}: DocumentCardProps) {
  const [confirmDelete, setConfirmDelete] = useState(false);

  const handleDelete = () => {
    if (confirmDelete) {
      onDelete(document.id);
      setConfirmDelete(false);
    } else {
      setConfirmDelete(true);
      setTimeout(() => setConfirmDelete(false), 3000);
    }
  };

  return (
    <div className="card-base flex flex-col gap-3 hover:border-primary/30 transition-colors group">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3 min-w-0">
          <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg bg-primary/10">
            <FileText className="h-5 w-5 text-primary" />
          </div>
          <div className="min-w-0">
            <p
              className="font-medium text-sm truncate max-w-[200px]"
              title={document.original_filename}
            >
              {document.original_filename}
            </p>
            <div className="flex items-center gap-2 mt-1">
              <span className="text-xs text-muted-foreground uppercase font-medium">
                {document.file_type}
              </span>
              <span className="text-muted-foreground/30">•</span>
              <span className="text-xs text-muted-foreground">
                {formatBytes(document.file_size_bytes)}
              </span>
            </div>
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          {(document.status === "pending" || document.status === "failed") && (
            <button
              onClick={() => onProcess(document.id)}
              disabled={isProcessing}
              className="rounded-md p-1.5 text-muted-foreground hover:bg-primary/10 hover:text-primary transition-colors disabled:opacity-50"
              title="Index document"
            >
              <RefreshCw className={cn("h-4 w-4", isProcessing && "animate-spin")} />
            </button>
          )}
          <button
            onClick={handleDelete}
            disabled={isDeleting}
            className={cn(
              "rounded-md p-1.5 transition-colors",
              confirmDelete
                ? "bg-red-500/20 text-red-500"
                : "text-muted-foreground hover:bg-red-500/10 hover:text-red-500"
            )}
            title={confirmDelete ? "Click again to confirm" : "Delete"}
          >
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Stats */}
      <div className="flex items-center gap-4 text-xs text-muted-foreground">
        {document.page_count && (
          <span>{document.page_count} pages</span>
        )}
        {document.chunk_count > 0 && (
          <span>{document.chunk_count} chunks</span>
        )}
        {document.word_count && (
          <span>{document.word_count.toLocaleString()} words</span>
        )}
      </div>

      {/* Status + time */}
      <div className="flex items-center justify-between">
        <div
          className={cn(
            "flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium",
            getStatusBadgeClass(document.status)
          )}
        >
          <StatusIcon status={document.status} />
          {document.status.charAt(0).toUpperCase() + document.status.slice(1)}
        </div>
        <span className="text-xs text-muted-foreground">
          {formatRelativeTime(document.created_at)}
        </span>
      </div>

      {document.error_message && (
        <p className="text-xs text-red-500 bg-red-500/10 rounded-md px-2.5 py-1.5">
          {document.error_message}
        </p>
      )}
    </div>
  );
}
