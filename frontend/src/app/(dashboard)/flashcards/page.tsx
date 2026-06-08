"use client";

import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { documentsApi } from "@/lib/api/documents";
import { toolsApi, Flashcard, FlashcardsResult } from "@/lib/api/tools";
import { queryKeys } from "@/lib/queryClient";
import { FileText, Loader2, Layers, ChevronLeft, ChevronRight, RotateCcw, CheckCheck, XCircle, Sparkles, AlertCircle } from "lucide-react";
import toast from "react-hot-toast";

export default function FlashcardsPage() {
  const [selectedDocId, setSelectedDocId] = useState("");
  const [numCards, setNumCards] = useState(10);
  const [result, setResult] = useState<FlashcardsResult | null>(null);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [flipped, setFlipped] = useState(false);
  const [known, setKnown] = useState<Set<number>>(new Set());
  const [unknown, setUnknown] = useState<Set<number>>(new Set());

  const { data: docsData, isLoading: docsLoading } = useQuery({
    queryKey: queryKeys.documents.list({ limit: 100 }),
    queryFn: () => documentsApi.list({ limit: 100 }),
  });
  const allDocs = docsData?.items ?? [];

  const mutation = useMutation({
    mutationFn: () =>
      toolsApi.flashcards({
        document_ids: selectedDocId ? [selectedDocId] : [],
        num_items: numCards,
      }),
    onSuccess: (data) => {
      setResult(data);
      setCurrentIndex(0);
      setFlipped(false);
      setKnown(new Set());
      setUnknown(new Set());
    },
    onError: () => toast.error("Failed to generate flashcards. Please try again."),
  });

  const card: Flashcard | null = result?.cards[currentIndex] ?? null;
  const total = result?.cards.length ?? 0;

  const goNext = () => { setFlipped(false); setTimeout(() => setCurrentIndex((i) => Math.min(i + 1, total - 1)), 150); };
  const goPrev = () => { setFlipped(false); setTimeout(() => setCurrentIndex((i) => Math.max(i - 1, 0)), 150); };

  const markKnown = () => {
    setKnown((s) => new Set([...s, currentIndex]));
    setUnknown((s) => { const n = new Set(s); n.delete(currentIndex); return n; });
    if (currentIndex < total - 1) goNext();
  };
  const markUnknown = () => {
    setUnknown((s) => new Set([...s, currentIndex]));
    setKnown((s) => { const n = new Set(s); n.delete(currentIndex); return n; });
    if (currentIndex < total - 1) goNext();
  };

  const progress = total > 0 ? ((known.size + unknown.size) / total) * 100 : 0;

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      {/* Header */}
      <div className="border-b border-border bg-card/50 px-6 py-4">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-amber-500/10">
            <Layers className="h-5 w-5 text-amber-500" />
          </div>
          <div>
            <h1 className="text-lg font-semibold">Flashcards</h1>
            <p className="text-xs text-muted-foreground">Active recall study mode</p>
          </div>
        </div>
      </div>

      <div className="flex-1 p-6 max-w-2xl mx-auto w-full space-y-6">
        {/* Setup */}
        {!result && (
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
                  <label className={`flex items-center gap-3 rounded-lg border px-3 py-2.5 cursor-pointer transition-colors ${selectedDocId === "" ? "border-amber-500 bg-amber-500/10" : "border-border hover:bg-accent"}`}>
                    <input type="radio" name="doc-flash" value="" checked={selectedDocId === ""} onChange={() => setSelectedDocId("")} className="accent-amber-500" />
                    <FileText className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                    <span className="text-sm font-medium flex-1">All documents</span>
                  </label>
                  {allDocs.map((doc) => (
                    <label key={doc.id} className={`flex items-center gap-3 rounded-lg border px-3 py-2.5 cursor-pointer transition-colors ${selectedDocId === doc.id ? "border-amber-500 bg-amber-500/10" : "border-border hover:bg-accent"}`}>
                      <input type="radio" name="doc-flash" value={doc.id} checked={selectedDocId === doc.id} onChange={() => setSelectedDocId(doc.id)} className="accent-amber-500" />
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

            <div>
              <label className="block text-sm font-medium mb-1.5">Number of Cards</label>
              <select className="w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50" value={numCards} onChange={(e) => setNumCards(Number(e.target.value))}>
                {[5, 10, 15, 20].map((n) => <option key={n} value={n}>{n} cards</option>)}
              </select>
            </div>

            <button
              onClick={() => mutation.mutate()}
              disabled={mutation.isPending || allDocs.length === 0}
              className="flex w-full items-center justify-center gap-2 rounded-xl bg-amber-500 px-4 py-2.5 text-sm font-medium text-white hover:bg-amber-600 disabled:opacity-60 transition-colors"
            >
              {mutation.isPending ? (
                <><Loader2 className="h-4 w-4 animate-spin" /> Generating Cards…</>
              ) : (
                <><Sparkles className="h-4 w-4" /> Generate Flashcards</>
              )}
            </button>
          </div>
        )}

        {/* Study mode */}
        {result && card && (
          <div className="space-y-4">
            {/* Progress */}
            <div className="space-y-1.5">
              <div className="flex justify-between text-xs text-muted-foreground">
                <span>Card {currentIndex + 1} of {total}</span>
                <span>{known.size} known · {unknown.size} to review</span>
              </div>
              <div className="h-1.5 rounded-full bg-muted overflow-hidden">
                <div className="h-full rounded-full bg-amber-500 transition-all duration-300" style={{ width: `${progress}%` }} />
              </div>
            </div>

            {/* Topic chip */}
            <div className="flex justify-center">
              <span className="rounded-full bg-amber-500/10 text-amber-600 dark:text-amber-400 text-xs px-3 py-1 font-medium capitalize">{card.topic}</span>
            </div>

            {/* Flip card */}
            <div className="cursor-pointer select-none" onClick={() => setFlipped((f) => !f)} style={{ perspective: "1200px" }}>
              <div className="relative w-full transition-transform duration-500" style={{ transformStyle: "preserve-3d", transform: flipped ? "rotateY(180deg)" : "rotateY(0deg)", minHeight: "220px" }}>
                {/* Front */}
                <div className="absolute inset-0 rounded-2xl border-2 border-amber-500/30 bg-card flex flex-col items-center justify-center p-8 text-center" style={{ backfaceVisibility: "hidden" }}>
                  <p className="text-xs text-muted-foreground mb-3 uppercase tracking-wider">Question</p>
                  <p className="text-lg font-semibold leading-snug">{card.front}</p>
                  <p className="mt-6 text-xs text-muted-foreground">Click to reveal answer</p>
                </div>
                {/* Back */}
                <div className="absolute inset-0 rounded-2xl border-2 border-emerald-500/30 bg-emerald-500/5 flex flex-col items-center justify-center p-8 text-center" style={{ backfaceVisibility: "hidden", transform: "rotateY(180deg)" }}>
                  <p className="text-xs text-muted-foreground mb-3 uppercase tracking-wider">Answer</p>
                  <p className="text-base leading-relaxed text-foreground">{card.back}</p>
                </div>
              </div>
            </div>

            {/* Navigation */}
            <div className="flex items-center justify-between gap-3">
              <button onClick={goPrev} disabled={currentIndex === 0} className="flex items-center gap-1.5 rounded-xl border border-border px-4 py-2 text-sm font-medium hover:bg-accent disabled:opacity-40 transition-colors">
                <ChevronLeft className="h-4 w-4" /> Prev
              </button>

              {flipped && (
                <div className="flex gap-2">
                  <button onClick={markUnknown} className="flex items-center gap-1.5 rounded-xl bg-red-500/10 border border-red-500/30 px-4 py-2 text-sm font-medium text-red-500 hover:bg-red-500/20 transition-colors">
                    <XCircle className="h-4 w-4" /> Still Learning
                  </button>
                  <button onClick={markKnown} className="flex items-center gap-1.5 rounded-xl bg-emerald-500/10 border border-emerald-500/30 px-4 py-2 text-sm font-medium text-emerald-500 hover:bg-emerald-500/20 transition-colors">
                    <CheckCheck className="h-4 w-4" /> Got It
                  </button>
                </div>
              )}

              <button onClick={goNext} disabled={currentIndex === total - 1} className="flex items-center gap-1.5 rounded-xl border border-border px-4 py-2 text-sm font-medium hover:bg-accent disabled:opacity-40 transition-colors">
                Next <ChevronRight className="h-4 w-4" />
              </button>
            </div>

            {/* Done */}
            {known.size + unknown.size === total && (
              <div className="rounded-xl bg-muted/50 p-4 text-center space-y-3">
                <p className="font-semibold">Deck complete! 🎉</p>
                <p className="text-sm text-muted-foreground">{known.size} known · {unknown.size} to review</p>
                <button onClick={() => { setResult(null); setKnown(new Set()); setUnknown(new Set()); }} className="flex items-center gap-2 mx-auto rounded-xl border border-border px-4 py-2 text-sm font-medium hover:bg-accent transition-colors">
                  <RotateCcw className="h-4 w-4" /> New Deck
                </button>
              </div>
            )}

            {!flipped && known.size + unknown.size < total && (
              <p className="text-xs text-center text-muted-foreground">Click the card to reveal the answer</p>
            )}

            <p className="text-xs text-muted-foreground text-right">Generated in {(result.latency_ms / 1000).toFixed(1)}s</p>
          </div>
        )}
      </div>
    </div>
  );
}
