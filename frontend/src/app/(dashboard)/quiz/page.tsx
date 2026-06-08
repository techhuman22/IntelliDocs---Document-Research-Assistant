"use client";

import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { documentsApi } from "@/lib/api/documents";
import { toolsApi, QuizResult, QuizQuestion } from "@/lib/api/tools";
import { queryKeys } from "@/lib/queryClient";
import { FileText, Loader2, GraduationCap, CheckCircle2, XCircle, RotateCcw, Trophy, AlertCircle } from "lucide-react";
import toast from "react-hot-toast";
import { cn } from "@/lib/utils";

type AnswerState = Record<number, string | null>;

export default function QuizPage() {
  const [selectedDocId, setSelectedDocId] = useState("");
  const [numQuestions, setNumQuestions] = useState(5);
  const [difficulty, setDifficulty] = useState("mixed");
  const [result, setResult] = useState<QuizResult | null>(null);
  const [answers, setAnswers] = useState<AnswerState>({});
  const [submitted, setSubmitted] = useState(false);

  const { data: docsData, isLoading: docsLoading } = useQuery({
    queryKey: queryKeys.documents.list({ limit: 100 }),
    queryFn: () => documentsApi.list({ limit: 100 }),
  });
  const allDocs = docsData?.items ?? [];

  const mutation = useMutation({
    mutationFn: () =>
      toolsApi.quiz({
        document_ids: selectedDocId ? [selectedDocId] : [],
        num_items: numQuestions,
        difficulty,
      }),
    onSuccess: (data) => { setResult(data); setAnswers({}); setSubmitted(false); },
    onError: () => toast.error("Failed to generate quiz. Please try again."),
  });

  const handleAnswer = (questionNumber: number, label: string) => {
    if (submitted) return;
    setAnswers((prev) => ({ ...prev, [questionNumber]: label }));
  };

  const score = result
    ? result.questions.filter((q) => {
        if (q.options.length === 0) return false;
        return answers[q.question_number] === q.options.find((o) => o.is_correct)?.label;
      }).length
    : 0;

  const totalMCQ = result?.questions.filter((q) => q.options.length > 0).length ?? 0;

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      {/* Header */}
      <div className="border-b border-border bg-card/50 px-6 py-4">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-violet-500/10">
            <GraduationCap className="h-5 w-5 text-violet-500" />
          </div>
          <div>
            <h1 className="text-lg font-semibold">Quiz Generator</h1>
            <p className="text-xs text-muted-foreground">Test your knowledge with AI-generated questions</p>
          </div>
        </div>
      </div>

      <div className="flex-1 p-6 max-w-3xl mx-auto w-full space-y-6">
        {/* Setup */}
        {!result && (
          <div className="rounded-xl border border-border bg-card p-5 space-y-4">
            {/* Doc picker */}
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
                  <label className={`flex items-center gap-3 rounded-lg border px-3 py-2.5 cursor-pointer transition-colors ${selectedDocId === "" ? "border-violet-500 bg-violet-500/10" : "border-border hover:bg-accent"}`}>
                    <input type="radio" name="doc-quiz" value="" checked={selectedDocId === ""} onChange={() => setSelectedDocId("")} className="accent-violet-500" />
                    <FileText className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                    <span className="text-sm font-medium flex-1">All documents</span>
                  </label>
                  {allDocs.map((doc) => (
                    <label key={doc.id} className={`flex items-center gap-3 rounded-lg border px-3 py-2.5 cursor-pointer transition-colors ${selectedDocId === doc.id ? "border-violet-500 bg-violet-500/10" : "border-border hover:bg-accent"}`}>
                      <input type="radio" name="doc-quiz" value={doc.id} checked={selectedDocId === doc.id} onChange={() => setSelectedDocId(doc.id)} className="accent-violet-500" />
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

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium mb-1.5">Number of Questions</label>
                <select className="w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50" value={numQuestions} onChange={(e) => setNumQuestions(Number(e.target.value))}>
                  {[3, 5, 8, 10, 15].map((n) => <option key={n} value={n}>{n} questions</option>)}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium mb-1.5">Difficulty</label>
                <select className="w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50" value={difficulty} onChange={(e) => setDifficulty(e.target.value)}>
                  <option value="mixed">Mixed</option>
                  <option value="easy">Easy</option>
                  <option value="medium">Medium</option>
                  <option value="hard">Hard</option>
                </select>
              </div>
            </div>

            <button
              onClick={() => mutation.mutate()}
              disabled={mutation.isPending || allDocs.length === 0}
              className="flex w-full items-center justify-center gap-2 rounded-xl bg-violet-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-violet-700 disabled:opacity-60 transition-colors"
            >
              {mutation.isPending ? (
                <><Loader2 className="h-4 w-4 animate-spin" /> Generating Quiz…</>
              ) : (
                <><GraduationCap className="h-4 w-4" /> Generate Quiz</>
              )}
            </button>
          </div>
        )}

        {/* Score */}
        {result && submitted && (
          <div className="rounded-xl border border-violet-500/20 bg-violet-500/5 p-5 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Trophy className="h-8 w-8 text-violet-500" />
              <div>
                <p className="font-semibold">Quiz Complete!</p>
                <p className="text-sm text-muted-foreground">{result.topic} · {result.difficulty}</p>
              </div>
            </div>
            <div className="text-right">
              <p className="text-2xl font-bold text-violet-500">{score}/{totalMCQ}</p>
              <p className="text-xs text-muted-foreground">MCQ correct</p>
            </div>
          </div>
        )}

        {/* Questions */}
        {result && (
          <div className="space-y-4">
            {result.questions.map((q) => (
              <QuestionCard key={q.question_number} question={q} chosen={answers[q.question_number] ?? null} submitted={submitted} onAnswer={(label) => handleAnswer(q.question_number, label)} />
            ))}
            <div className="flex gap-3 pt-2">
              {!submitted && (
                <button onClick={() => setSubmitted(true)} disabled={Object.keys(answers).length === 0} className="flex-1 rounded-xl bg-violet-600 py-2.5 text-sm font-medium text-white hover:bg-violet-700 disabled:opacity-50 transition-colors">
                  Submit Answers
                </button>
              )}
              <button onClick={() => { setResult(null); setAnswers({}); setSubmitted(false); }} className="flex items-center gap-2 rounded-xl border border-border px-4 py-2.5 text-sm font-medium hover:bg-accent transition-colors">
                <RotateCcw className="h-4 w-4" /> New Quiz
              </button>
            </div>
            <p className="text-xs text-muted-foreground text-right">Generated in {(result.latency_ms / 1000).toFixed(1)}s</p>
          </div>
        )}
      </div>
    </div>
  );
}

function QuestionCard({ question, chosen, submitted, onAnswer }: { question: QuizQuestion; chosen: string | null; submitted: boolean; onAnswer: (label: string) => void; }) {
  const correct = question.options.find((o) => o.is_correct)?.label;
  const isMCQ = question.options.length > 0;

  return (
    <div className="rounded-xl border border-border bg-card p-5 space-y-3">
      <div className="flex items-start gap-3">
        <span className="flex-shrink-0 flex h-6 w-6 items-center justify-center rounded-full bg-violet-500/10 text-violet-500 text-xs font-bold">{question.question_number}</span>
        <div className="flex-1">
          <p className="text-sm font-medium leading-relaxed">{question.question}</p>
          <div className="flex gap-2 mt-1">
            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-muted text-muted-foreground capitalize">{question.question_type}</span>
            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-muted text-muted-foreground capitalize">{question.difficulty}</span>
          </div>
        </div>
      </div>

      {isMCQ ? (
        <div className="space-y-2 pl-9">
          {question.options.map((opt) => {
            const isChosen = chosen === opt.label;
            const isCorrect = opt.is_correct;
            let optClass = "border-border bg-background hover:bg-accent";
            if (submitted) {
              if (isCorrect) optClass = "border-emerald-500 bg-emerald-500/10";
              else if (isChosen && !isCorrect) optClass = "border-red-500 bg-red-500/10";
            } else if (isChosen) {
              optClass = "border-violet-500 bg-violet-500/10";
            }
            return (
              <button key={opt.label} onClick={() => onAnswer(opt.label)} className={cn("w-full flex items-center gap-3 rounded-lg border px-3 py-2 text-sm text-left transition-all", optClass)}>
                <span className="font-medium text-xs w-4 flex-shrink-0">{opt.label}</span>
                <span className="flex-1">{opt.text}</span>
                {submitted && isCorrect && <CheckCircle2 className="h-4 w-4 text-emerald-500 flex-shrink-0" />}
                {submitted && isChosen && !isCorrect && <XCircle className="h-4 w-4 text-red-500 flex-shrink-0" />}
              </button>
            );
          })}
        </div>
      ) : (
        <div className="pl-9">
          {submitted ? (
            <div className="rounded-lg bg-muted/50 p-3 text-sm text-muted-foreground">
              <p className="text-xs font-semibold text-foreground mb-1">Model Answer:</p>
              <p>{question.answer}</p>
            </div>
          ) : (
            <p className="text-xs text-muted-foreground italic">Open-ended — answer mentally, then submit to reveal.</p>
          )}
        </div>
      )}

      {submitted && (
        <div className="pl-9 rounded-lg bg-muted/30 p-3 text-xs text-muted-foreground">
          <span className="font-semibold text-foreground">Explanation: </span>{question.explanation}
        </div>
      )}
    </div>
  );
}
