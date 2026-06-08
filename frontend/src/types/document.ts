export type DocumentStatus = "pending" | "processing" | "ready" | "failed";

export interface Document {
  id: string;
  original_filename: string;
  file_type: string;
  mime_type: string;
  file_size_bytes: number;
  status: DocumentStatus;
  error_message: string | null;
  page_count: number | null;
  word_count: number | null;
  chunk_count: number;
  created_at: string;
  updated_at: string;
}

export interface DocumentListResponse {
  items: Document[];
  total: number;
  page: number;
  limit: number;
  total_pages: number;
  has_next: boolean;
  has_prev: boolean;
}

export interface StorageStats {
  total_bytes: number | string;
  total_mb: number | string;
  document_count: number;
  quota_bytes: number;
  quota_mb: number;
  usage_percent: number | string;
}

export interface ProcessingStatusResponse {
  document_id: string;
  status: DocumentStatus;
  message: string;
  chunk_count: number;
  error_message: string | null;
}
