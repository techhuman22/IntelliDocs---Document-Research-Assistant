import { apiClient } from "./axios";

export interface ToolRequest {
  document_ids?: string[];
  query?: string;
  num_items?: number;
  difficulty?: string;
}

export interface SummaryResult {
  short_summary: string;
  detailed_summary: string;
  bullet_points: string[];
  key_topics: string[];
  word_count: number;
  latency_ms: number;
}

export interface QuizOption {
  label: string;
  text: string;
  is_correct: boolean;
}

export interface QuizQuestion {
  question_number: number;
  question_type: string;
  difficulty: string;
  question: string;
  options: QuizOption[];
  answer: string;
  explanation: string;
}

export interface QuizResult {
  topic: string;
  difficulty: string;
  total_questions: number;
  questions: QuizQuestion[];
  latency_ms: number;
}

export interface Citation {
  source_number: number;
  filename: string;
  chunk_index: number;
  page_number: number | null;
  similarity_score: number;
}

export interface QAResult {
  answer: string;
  citations: Citation[];
  latency_ms: number;
}

export interface Flashcard {
  front: string;
  back: string;
  topic: string;
}

export interface FlashcardsResult {
  cards: Flashcard[];
  total: number;
  latency_ms: number;
}

const TOOLS_TIMEOUT = 120_000; // 2 minutes — LLM structured output can be slow

export const toolsApi = {
  summary: async (body: ToolRequest): Promise<SummaryResult> => {
    const { data } = await apiClient.post<SummaryResult>("/api/v1/tools/summary", body, { timeout: TOOLS_TIMEOUT });
    return data;
  },

  quiz: async (body: ToolRequest): Promise<QuizResult> => {
    const { data } = await apiClient.post<QuizResult>("/api/v1/tools/quiz", body, { timeout: TOOLS_TIMEOUT });
    return data;
  },

  qa: async (body: ToolRequest): Promise<QAResult> => {
    const { data } = await apiClient.post<QAResult>("/api/v1/tools/qa", body, { timeout: TOOLS_TIMEOUT });
    return data;
  },

  flashcards: async (body: ToolRequest): Promise<FlashcardsResult> => {
    const { data } = await apiClient.post<FlashcardsResult>("/api/v1/tools/flashcards", body, { timeout: TOOLS_TIMEOUT });
    return data;
  },
};
