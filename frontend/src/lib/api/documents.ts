import apiClient from "./axios";
import type {
  Document,
  DocumentListResponse,
  ProcessingStatusResponse,
  StorageStats,
} from "@/types/document";

export const documentsApi = {
  upload: async (
    file: File,
    onProgress?: (percent: number) => void
  ): Promise<Document> => {
    const formData = new FormData();
    formData.append("file", file);
    const response = await apiClient.post<Document>(
      "/api/v1/documents/upload",
      formData,
      {
        headers: { "Content-Type": "multipart/form-data" },
        onUploadProgress: (e) => {
          if (e.total && onProgress) {
            onProgress(Math.round((e.loaded * 100) / e.total));
          }
        },
      }
    );
    return response.data;
  },

  list: async (params?: {
    page?: number;
    limit?: number;
    status?: string;
  }): Promise<DocumentListResponse> => {
    const response = await apiClient.get<DocumentListResponse>(
      "/api/v1/documents",
      { params }
    );
    return response.data;
  },

  get: async (id: string): Promise<Document> => {
    const response = await apiClient.get<Document>(`/api/v1/documents/${id}`);
    return response.data;
  },

  delete: async (id: string): Promise<void> => {
    await apiClient.delete(`/api/v1/documents/${id}`);
  },

  triggerProcessing: async (
    id: string,
    force = false
  ): Promise<ProcessingStatusResponse> => {
    const response = await apiClient.post<ProcessingStatusResponse>(
      `/api/v1/documents/process/${id}`,
      null,
      { params: { force } }
    );
    return response.data;
  },

  getStorageStats: async (): Promise<StorageStats> => {
    const response = await apiClient.get<StorageStats>(
      "/api/v1/documents/storage/stats"
    );
    return response.data;
  },
};
