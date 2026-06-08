"use client";

import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { documentsApi } from "@/lib/api/documents";
import { toolsApi, SummaryResult } from "@/lib/api/tools";
import { queryKeys } from "@/lib/queryClient";
import { FileText, Sparkles, Loader2, BookOpen, ListChecks, Tag, AlertCircle } from "lucide-react";
import toast from "react-hot-toast";

export default function SummaryPage() {
  const [selectedDocId, setSelectedDocId] = useState<string>("");
  const [result, setResult] = useState<SummaryResult | null>(null);

  const { data: docsData, isLoading: docsLoading } = useQuery({
    queryKey: queryKeys.documents.list({ limit: 100 }),
    queryFn: () => documentsApi.list({ limit: 100 }),
  });

  const allDocs = docsData?.items ?? [];
  const readyDocs = allDocs.filter((d) => d.status === "ready");
  const selectedDoc = allDocs.find((d) => d.id === selectedDocId);
  const selectedNotReady = selectedDoc && selectedDoc.status !== "ready";
  const noReadyDocs = allDocs.length > 0 && readyDocs.length === 0;

  const mutation = useMutation({
    mutationFn: () =>
      toolsApi.summary({
        document_ids: selectedDocId ? [selectedDocId] : [],
      }),
    onSuccess: (data) => setResult(data),
    onError: (err: any) => {
      const msg = err?.response?.data?.detail || "Failed to generate summary. Please try again.";
      toast.error(msg);
    },
  });

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      {/* Header */}
      <div className="border-b border-border bg-card/50 px-6 py-4">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-blue-500/10">
            <BookOpen className="h-5 w-5 text-blue-500" />
          </div>
          <div>
            <h1 className="text-lg font-semibold">Document Summary</h1>
            <p className="text-xs text-muted-foreground">AI-generated summaries from your documents</p>
          </div>
        </div>
      </div>

      <div className="flex-1 p-6 max-w-3xl mx-auto w-full space-y-6">
        {/* Controls */}
        <div className="rounded-xl border border-border bg-card p-5 space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1.5">Select Document</label>
            {docsLoading ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground py-2">
                <Loader2 className="h-4 w-4 animate-spin" /> Loading documents…
              </div>
            ) : allDocs.length === 0 ? (
              <div className="flex items-center gap-2 text-sm text-amber-500 rounded-lg bg-amber-500/10 px-3 py-2">
                <AlertCircle className="h-4 w-4 flex-shrink-0" />
                No documents found. Upload a document first.
              </div>
            ) : (
              <div className="space-y-2">
                {/* All docs option */}
                <label className={`flex items-center gap-3 rounded-lg border px-3 py-2.5 cursor-pointer transition-colors ${selectedDocId === "" ? "border-blue-500 bg-blue-500/10" : "border-border hover:bg-accent"}`}>
                  <input type="radio" name="doc" value="" checked={selectedDocId === ""} onChange={() => { setSelectedDocId(""); setResult(null); }} className="accent-blue-500" />
                  <FileText className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                  <span className="text-sm font-medium flex-1">All documents</span>
                </label>
                {allDocs.map((doc) => (
                  <label key={doc.id} className={`flex items-center gap-3 rounded-lg border px-3 py-2.5 cursor-pointer transition-colors ${selectedDocId === doc.id ? "border-blue-500 bg-blue-500/10" : "border-border hover:bg-accent"}`}>
                    <input type="radio" name="doc" value={doc.id} checked={selectedDocId === doc.id} onChange={() => { setSelectedDocId(doc.id); setResult(null); }} className="accent-blue-500" />
                    <FileText className="h-4 w-4 text-primary flex-shrink-0" />
                    <span className="text-sm flex-1 truncate">{doc.original_filename}</span>
                    <span className={`text-[10px] px-2 py-0.5 rounded-full flex-shrink-0 font-medium ${doc.status === "ready" ? "bg-emerald-500/10 text-emerald-500" : doc.status === "processing" ? "bg-blue-500/10 text-blue-500" : "bg-amber-500/10 text-amber-500"}`}>
                      {doc.status}
                    </span>
                  </label>
                ))}
              </div>
            )}
          </div>

          {selectedNotReady && (
            <div className="flex items-center gap-2 text-xs text-amber-500 rounded-lg bg-amber-500/10 px-3 py-2">
              <AlertCircle className="h-3.5 w-3.5 flex-shrink-0" />
              This document is not processed yet. Go to Documents page and click Process.
            </div>
          )}

          <button
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending || allDocs.length === 0}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60 transition-colors"
          >
            {mutation.isPending ? (
              <><Loader2 className="h-4 w-4 animate-spin" /> Generating Summary…</>
            ) : (
              <><Sparkles className="h-4 w-4" /> Generate Summary</>
            )}
          </button>
        </div>

        {/* Result */}
        {result && (
          <div className="space-y-4">
            {/* Short summary */}
            <div className="rounded-xl border border-blue-500/20 bg-blue-500/5 p-5">
              <p className="text-xs font-semibold text-blue-500 mb-2 uppercase tracking-wider">Overview</p>
              <p className="text-sm leading-relaxed">{result.short_summary}</p>
            </div>

            {/* Key topics */}
            <div className="rounded-xl border border-border bg-card p-5">
              <div className="flex items-center gap-2 mb-3">
                <Tag className="h-4 w-4 text-primary" />
                <span className="text-sm font-semibold">Key Topics</span>
              </div>
              <div className="flex flex-wrap gap-2">
                {result.key_topics.map((topic, i) => (
                  <span key={i} className="rounded-full bg-primary/10 text-primary text-xs px-3 py-1 font-medium">
                    {topic}
                  </span>
                ))}
              </div>
            </div>

            {/* Bullet points */}
            <div className="rounded-xl border border-border bg-card p-5">
              <div className="flex items-center gap-2 mb-3">
                <ListChecks className="h-4 w-4 text-primary" />
                <span className="text-sm font-semibold">Key Takeaways</span>
              </div>
              <ul className="space-y-2">
                {result.bullet_points.map((point, i) => (
                  <li key={i} className="flex items-start gap-2.5 text-sm">
                    <span className="mt-1.5 h-1.5 w-1.5 rounded-full bg-primary flex-shrink-0" />
                    <span className="text-muted-foreground leading-relaxed">{point}</span>
                  </li>
                ))}
              </ul>
            </div>

            {/* Detailed summary */}
            <div className="rounded-xl border border-border bg-card p-5">
              <div className="flex items-center gap-2 mb-3">
                <BookOpen className="h-4 w-4 text-primary" />
                <span className="text-sm font-semibold">Detailed Summary</span>
                <span className="ml-auto text-xs text-muted-foreground">{result.word_count} words</span>
              </div>
              <p className="text-sm leading-relaxed text-muted-foreground whitespace-pre-line">{result.detailed_summary}</p>
            </div>

            <p className="text-xs text-muted-foreground text-right">Generated in {(result.latency_ms / 1000).toFixed(1)}s</p>
          </div>
        )}
      </div>
    </div>
  );
}
