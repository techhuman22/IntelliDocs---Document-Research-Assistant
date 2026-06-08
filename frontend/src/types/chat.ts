export type Intent = "qa" | "summary" | "quiz" | "unknown";

export interface Citation {
  position: number;
  document_id: string;
  original_filename: string;
  page_number: number | null;
  chunk_index: number;
  similarity_score: number;
}

export interface AgentTraceEntry {
  agent_name: string;
  status: "success" | "error" | "skipped";
  latency_ms: number | null;
  token_input: number | null;
  token_output: number | null;
}

export interface QuizOption {
  label: string;
  text: string;
  is_correct: boolean;
}

export interface QuizQuestion {
  question_number: number;
  question_type: "mcq" | "conceptual" | "interview";
  difficulty: "easy" | "medium" | "hard";
  question: string;
  options: QuizOption[];
  answer: string;
  explanation: string;
}

export interface QuizOutput {
  topic: string;
  difficulty: string;
  total_questions: number;
  questions: QuizQuestion[];
}

export interface SummaryOutput {
  short_summary: string;
  detailed_summary: string;
  bullet_points: string[];
  key_topics: string[];
  word_count: number;
}

export interface ChatResponse {
  session_id: string;
  message_id: string;
  query: string;
  intent: Intent;
  response: string;
  structured_data: QuizOutput | SummaryOutput | null;
  citations: Citation[];
  agent_trace: AgentTraceEntry[];
  latency_ms: number;
  token_count: number | null;
}

export interface ChatMessage {
  id: string;
  session_id: string;
  role: "user" | "assistant";
  content: string;
  content_type: "text" | "summary" | "quiz";
  intent: Intent | null;
  structured_data: QuizOutput | SummaryOutput | null;
  sources: Citation[] | null;
  agent_path: string[] | null;
  latency_ms: number | null;
  created_at: string;
}

export interface ChatSession {
  id: string;
  title: string | null;
  document_ids: string[];
  session_type: string;
  message_count: number;
  last_active_at: string;
  is_archived: boolean;
  created_at: string;
}

export interface SessionListResponse {
  sessions: ChatSession[];
  total: number;
  page: number;
  limit: number;
}

export interface MessageHistoryResponse {
  session_id: string;
  messages: ChatMessage[];
  total: number;
  page: number;
  limit: number;
}

// Streaming event shapes
export type StreamEventType = "agent_start" | "agent_end" | "token" | "final" | "error";

export interface StreamEvent {
  event_type: StreamEventType;
  data: Record<string, unknown>;
}

// Client-side chat state (not from API)
export interface ClientMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  intent?: Intent;
  citations?: Citation[];
  agent_trace?: AgentTraceEntry[];
  structured_data?: QuizOutput | SummaryOutput | null;
  latency_ms?: number;
  isStreaming?: boolean;
  created_at: string;
}
