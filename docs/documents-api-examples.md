# Document Management API — Example Requests & Responses

Base URL: `http://localhost:8000/api/v1`

All endpoints require: `Authorization: Bearer <access_token>`

---

## 1. Upload a Document

```bash
curl -X POST http://localhost:8000/api/v1/documents/upload \
  -H "Authorization: Bearer eyJhbGci..." \
  -F "file=@/path/to/report.pdf"
```

**201 Created**
```json
{
  "document_id": "b3c4d5e6-f7a8-9012-bcde-f12345678901",
  "original_filename": "report.pdf",
  "file_type": "pdf",
  "file_size_bytes": 245760,
  "status": "pending",
  "message": "File uploaded successfully. Processing will begin shortly."
}
```

**413 — File too large**
```json
{
  "error": {
    "code": "FILE_TOO_LARGE",
    "message": "File exceeds the maximum allowed size of 50 MB.",
    "details": { "max_size_mb": 50 }
  }
}
```

**415 — Unsupported file type**
```json
{
  "error": {
    "code": "UNSUPPORTED_FILE_TYPE",
    "message": "File type 'exe' is not supported.",
    "details": {
      "file_type": "exe",
      "allowed_types": ["pdf", "docx", "txt"]
    }
  }
}
```

---

## 2. List Documents

```bash
# Default (newest first, page 1, 20 per page)
curl http://localhost:8000/api/v1/documents \
  -H "Authorization: Bearer eyJhbGci..."

# With filters
curl "http://localhost:8000/api/v1/documents?status=ready&file_type=pdf&page=1&limit=10&sort_by=file_size_bytes&sort_order=desc" \
  -H "Authorization: Bearer eyJhbGci..."
```

**200 OK**
```json
{
  "items": [
    {
      "id": "b3c4d5e6-f7a8-9012-bcde-f12345678901",
      "original_filename": "report.pdf",
      "file_type": "pdf",
      "file_size_bytes": 245760,
      "file_size_mb": 0.23,
      "status": "ready",
      "chunk_count": 42,
      "created_at": "2024-01-15T10:30:00Z"
    },
    {
      "id": "c4d5e6f7-a8b9-0123-cdef-012345678902",
      "original_filename": "meeting-notes.txt",
      "file_type": "txt",
      "file_size_bytes": 8192,
      "file_size_mb": 0.01,
      "status": "pending",
      "chunk_count": 0,
      "created_at": "2024-01-15T09:00:00Z"
    }
  ],
  "total": 2,
  "page": 1,
  "limit": 20,
  "total_pages": 1,
  "has_next": false,
  "has_prev": false
}
```

---

## 3. Get Document Details

```bash
curl http://localhost:8000/api/v1/documents/b3c4d5e6-f7a8-9012-bcde-f12345678901 \
  -H "Authorization: Bearer eyJhbGci..."
```

**200 OK**
```json
{
  "id": "b3c4d5e6-f7a8-9012-bcde-f12345678901",
  "user_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "original_filename": "quarterly-report-q4.pdf",
  "file_type": "pdf",
  "mime_type": "application/pdf",
  "file_size_bytes": 245760,
  "file_size_mb": 0.23,
  "status": "ready",
  "is_ready": true,
  "error_message": null,
  "page_count": 18,
  "word_count": 4521,
  "chunk_count": 42,
  "doc_metadata": {
    "title": "Q4 2024 Quarterly Report",
    "author": "Finance Team"
  },
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:31:15Z"
}
```

**404 — Not found or belongs to another user**
```json
{
  "error": {
    "code": "DOCUMENT_NOT_FOUND",
    "message": "Document with id 'b3c4d5e6-...' not found.",
    "details": {
      "resource": "Document",
      "id": "b3c4d5e6-f7a8-9012-bcde-f12345678901"
    }
  }
}
```

---

## 4. Delete a Document

```bash
curl -X DELETE http://localhost:8000/api/v1/documents/b3c4d5e6-f7a8-9012-bcde-f12345678901 \
  -H "Authorization: Bearer eyJhbGci..."
```

**200 OK**
```json
{
  "message": "Document b3c4d5e6-f7a8-9012-bcde-f12345678901 deleted successfully."
}
```

---

## 5. Storage Statistics

```bash
curl http://localhost:8000/api/v1/documents/storage/stats \
  -H "Authorization: Bearer eyJhbGci..."
```

**200 OK**
```json
{
  "total_bytes": 2621440,
  "total_mb": 2.5,
  "document_count": 7,
  "quota_bytes": 1073741824,
  "quota_mb": 1024.0,
  "usage_percent": 0.2
}
```

---

## Document Processing Status Lifecycle

```
Upload (POST /upload)
        │
        ▼
   status: "pending"      ← DB record created, file on disk
        │
        ▼ (background worker — Phase 4)
   status: "processing"   ← text extraction running
        │
        ├──── success ──▶ status: "ready"   ← chunks created, queryable
        │
        └──── failure ──▶ status: "failed"  ← error_message populated
```

Poll `GET /documents/{id}` until status is `"ready"` before sending chat queries.
