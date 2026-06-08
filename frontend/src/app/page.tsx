import Link from "next/link";
import { Navbar } from "@/components/layout/Navbar";
import {
  Bot,
  Zap,
  Shield,
  BarChart3,
  FileText,
  BrainCircuit,
  ArrowRight,
} from "lucide-react";

// Note: ArrowRight kept — still used in the hero "Start for free" button

const features = [
  {
    icon: BrainCircuit,
    title: "Multi-Agent Pipeline",
    description:
      "Router, Retrieval, Summary, Quiz, and Response agents work in concert — each specialized for its task.",
  },
  {
    icon: Zap,
    title: "Instant Answers",
    description:
      "Ask any question about your documents and get cited, source-grounded answers in seconds.",
  },
  {
    icon: FileText,
    title: "Any Document Format",
    description:
      "Upload PDF, DOCX, or TXT. The pipeline extracts, chunks, and indexes every page automatically.",
  },
  {
    icon: BarChart3,
    title: "Smart Summaries",
    description:
      "Get short previews, detailed analyses, and bullet-point takeaways — tailored to your query.",
  },
  {
    icon: Shield,
    title: "Enterprise Security",
    description:
      "JWT dual-token auth, per-user document isolation, and encrypted storage out of the box.",
  },
  {
    icon: Bot,
    title: "Quiz Generation",
    description:
      "Instantly create MCQs, conceptual questions, and interview prep from any document content.",
  },
];

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-background">
      <Navbar />

      {/* Hero */}
      <section className="relative pt-32 pb-24 overflow-hidden">
        {/* Background gradient blobs */}
        <div className="pointer-events-none absolute -top-40 left-1/2 -translate-x-1/2 h-[600px] w-[800px] rounded-full bg-primary/10 blur-3xl" />
        <div className="pointer-events-none absolute top-20 right-0 h-[400px] w-[400px] rounded-full bg-violet-500/10 blur-3xl" />

        <div className="relative mx-auto max-w-5xl px-6 text-center">
          <h1 className="mb-6 text-5xl font-extrabold tracking-tight sm:text-7xl">
            <span className="gradient-text">IntelliDocs</span>
          </h1>

          <p className="mx-auto mb-10 max-w-2xl text-xl text-muted-foreground leading-relaxed">
            Upload documents, ask questions, get AI-powered answers with citations.
          </p>

          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link
              href="/register"
              className="flex items-center gap-2 rounded-xl bg-primary px-8 py-3.5 text-base font-semibold text-white hover:bg-primary/90 transition-all shadow-lg shadow-primary/25"
            >
              Start for free
              <ArrowRight className="h-5 w-5" />
            </Link>
            <Link
              href="/login"
              className="rounded-xl border border-border px-8 py-3.5 text-base font-semibold hover:bg-accent transition-colors"
            >
              Sign in
            </Link>
          </div>
        </div>

        {/* Hero image placeholder */}
        <div className="mx-auto mt-16 max-w-4xl px-6">
          <div className="glass-card p-1 shadow-2xl">
            <div className="rounded-xl bg-card p-6 h-64 flex items-center justify-center border border-border">
              <div className="text-center text-muted-foreground">
                <BrainCircuit className="mx-auto h-16 w-16 mb-4 text-primary/40" />
                <p className="text-sm">Multi-Agent Chat Interface</p>
                <p className="text-xs mt-1 text-muted-foreground/60">
                  Router → Retrieval → Summary / Quiz / QA → Response
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Features */}
      <section id="features" className="py-24 border-t border-border">
        <div className="mx-auto max-w-7xl px-6">
          <div className="mx-auto mb-16 max-w-2xl text-center">
            <h2 className="text-3xl font-bold tracking-tight sm:text-4xl mb-4">
              Everything you need to research smarter
            </h2>
            <p className="text-muted-foreground text-lg">
              Built on a production-grade RAG pipeline with LangGraph orchestration.
            </p>
          </div>
          <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {features.map((f) => (
              <div key={f.title} className="card-base group hover:border-primary/30 transition-colors">
                <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 group-hover:bg-primary/20 transition-colors">
                  <f.icon className="h-5 w-5 text-primary" />
                </div>
                <h3 className="mb-2 font-semibold">{f.title}</h3>
                <p className="text-sm text-muted-foreground leading-relaxed">
                  {f.description}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-border py-8">
        <div className="mx-auto max-w-7xl px-6 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <Bot className="h-5 w-5 text-primary" />
            <span className="font-semibold">IntelliDocs AI</span>
          </div>
          <p className="text-sm text-muted-foreground">
            © 2025 IntelliDocs AI. Built with Next.js + FastAPI + LangGraph.
          </p>
        </div>
      </footer>
    </div>
  );
}
