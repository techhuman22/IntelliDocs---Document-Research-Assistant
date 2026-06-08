"use client";

import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import { Upload, FileText, X, CheckCircle2 } from "lucide-react";
import { cn, formatBytes } from "@/lib/utils";

interface UploadFile {
  file: File;
  progress: number;
  status: "pending" | "uploading" | "done" | "error";
  error?: string;
}

interface UploadAreaProps {
  onUpload: (file: File, onProgress: (p: number) => void) => Promise<void>;
  maxSizeMb?: number;
  accept?: string[];
}

const ACCEPTED_TYPES: Record<string, string[]> = {
  "application/pdf": [".pdf"],
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"],
  "text/plain": [".txt"],
};

export function UploadArea({
  onUpload,
  maxSizeMb = 50,
  accept,
}: UploadAreaProps) {
  const [files, setFiles] = useState<UploadFile[]>([]);

  const onDrop = useCallback(
    async (acceptedFiles: File[]) => {
      const newFiles: UploadFile[] = acceptedFiles.map((f) => ({
        file: f,
        progress: 0,
        status: "pending",
      }));

      setFiles((prev) => [...prev, ...newFiles]);

      // Upload each file sequentially
      for (let i = 0; i < acceptedFiles.length; i++) {
        const file = acceptedFiles[i];
        const idx = files.length + i;

        setFiles((prev) =>
          prev.map((f, j) =>
            j === idx ? { ...f, status: "uploading" } : f
          )
        );

        try {
          await onUpload(file, (progress) => {
            setFiles((prev) =>
              prev.map((f, j) => (j === idx ? { ...f, progress } : f))
            );
          });

          setFiles((prev) =>
            prev.map((f, j) =>
              j === idx ? { ...f, status: "done", progress: 100 } : f
            )
          );
        } catch (err: unknown) {
          const message =
            err instanceof Error ? err.message : "Upload failed";
          setFiles((prev) =>
            prev.map((f, j) =>
              j === idx ? { ...f, status: "error", error: message } : f
            )
          );
        }
      }
    },
    [files.length, onUpload]
  );

  const { getRootProps, getInputProps, isDragActive, isDragReject } =
    useDropzone({
      onDrop,
      accept: ACCEPTED_TYPES,
      maxSize: maxSizeMb * 1024 * 1024,
      multiple: true,
    });

  const removeFile = (idx: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== idx));
  };

  return (
    <div className="flex flex-col gap-4">
      {/* Drop zone */}
      <div
        {...getRootProps()}
        className={cn(
          "flex cursor-pointer flex-col items-center gap-4 rounded-xl border-2 border-dashed p-10 transition-all duration-200",
          isDragActive && !isDragReject
            ? "border-primary bg-primary/5"
            : isDragReject
            ? "border-red-500 bg-red-500/5"
            : "border-border hover:border-primary/50 hover:bg-accent/50"
        )}
      >
        <input {...getInputProps()} />
        <div
          className={cn(
            "flex h-14 w-14 items-center justify-center rounded-2xl transition-colors",
            isDragActive ? "bg-primary/20" : "bg-muted"
          )}
        >
          <Upload
            className={cn(
              "h-7 w-7 transition-colors",
              isDragActive ? "text-primary" : "text-muted-foreground"
            )}
          />
        </div>
        <div className="text-center">
          <p className="font-semibold">
            {isDragActive
              ? "Drop files here"
              : "Drag & drop files, or click to browse"}
          </p>
          <p className="text-sm text-muted-foreground mt-1">
            PDF, DOCX, TXT — up to {maxSizeMb}MB each
          </p>
        </div>
      </div>

      {/* File list */}
      {files.length > 0 && (
        <ul className="space-y-2">
          {files.map((f, idx) => (
            <li
              key={idx}
              className="flex items-center gap-3 rounded-lg border border-border bg-card px-4 py-3"
            >
              <FileText className="h-5 w-5 flex-shrink-0 text-primary" />
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium truncate">
                    {f.file.name}
                  </span>
                  <span className="text-xs text-muted-foreground flex-shrink-0">
                    {formatBytes(f.file.size)}
                  </span>
                </div>

                {f.status === "uploading" && (
                  <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-muted">
                    <div
                      className="h-full rounded-full bg-primary transition-all duration-300"
                      style={{ width: `${f.progress}%` }}
                    />
                  </div>
                )}
                {f.status === "error" && (
                  <p className="mt-1 text-xs text-red-500">{f.error}</p>
                )}
              </div>

              {f.status === "done" ? (
                <CheckCircle2 className="h-5 w-5 flex-shrink-0 text-emerald-500" />
              ) : f.status !== "uploading" ? (
                <button
                  onClick={() => removeFile(idx)}
                  className="rounded-md p-1 text-muted-foreground hover:text-foreground"
                >
                  <X className="h-4 w-4" />
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
