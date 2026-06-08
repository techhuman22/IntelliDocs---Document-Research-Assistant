# RAG API Usage Examples

All endpoints require a JWT access token in the `Authorization: Bearer <token>` header.
Obtain a token via `POST /api/v1/auth/login`.

---

## 1. Upload a Document

```bash
curl -X POST http://localhost:8000/api/v1/documents/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@annual_report.pdf"
```

**Response**
```json
{
  "id": "a1b2c3d4-...",
  "original_filename": "annual_report.pdf",
  "status": "pending",
  "file_size_bytes": 1048576,
  "chunk_count": 0
}
```

---

## 2. Trigger RAG Indexing

```bash
curl -X POST \
  "http://localhost:8000/api/v1/documents/process/a1b2c3d4-..." \
  -H "Authorization: Bearer $TOKEN"
```

**Response (202 Accepted)**
```json
{
  "document_id": "a1b2c3d4-...",
  "status": "processing",
  "message": "Document queued for indexing. Check status via GET /documents/{id}.",
  "chunk_count": 0
}
```

> **Tip:** Poll `GET /api/v1/documents/{id}` until `status` is `"ready"`.

---

## 3. Check Document Status

```bash
curl "http://localhost:8000/api/v1/documents/a1b2c3d4-..." \
  -H "Authorization: Bearer $TOKEN"
```

**Response when ready**
```json
{
  "id": "a1b2c3d4-...",
  "status": "ready",
  "chunk_count": 142,
  "page_count": 38,
  "word_count": 21540
}
```

---

## 4. List Document Chunks

```bash
curl "http://localhost:8000/api/v1/documents/a1b2c3d4-.../chunks?page=1&limit=10" \
  -H "Authorization: Bearer $TOKEN"
```

**Response**
```json
{
  "document_id": "a1b2c3d4-...",
  "original_filename": "annual_report.pdf",
  "chunks": [
    {
      "id": "c1d2e3f4-...",
      "chunk_index": 0,
      "content": "AgentFlow Corporation Annual Report 2024. The company achieved record revenue growth of 43% year-over-year...",
      "token_count": 128,
      "char_count": 512,
      "page_number": 1
    }
  ],
  "total_chunks": 142,
  "page": 1,
  "limit": 10
}
```

---

## 5. Semantic Search (Retrieval)

```bash
curl -X POST http://localhost:8000/api/v1/retrieval/search \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What was the revenue growth in Q3?",
    "top_k": 5,
    "similarity_threshold": 0.72,
    "include_metadata": true
  }'
```

**Response**
```json
{
  "query": "What was the revenue growth in Q3?",
  "total_found": 5,
  "chunks": [
    {
      "chunk_id": "c1d2e3f4-...",
      "document_id": "a1b2c3d4-...",
      "original_filename": "annual_report.pdf",
      "chunk_index": 47,
      "content": "Q3 2024 revenue reached $124M, representing a 43% increase year-over-year driven primarily by enterprise contract expansion...",
      "similarity_score": 0.9312,
      "page_number": 12,
      "chunk_metadata": {
        "source_filename": "annual_report.pdf",
        "section": "Financial Results",
        "element_type": "text"
      }
    }
  ],
  "context": "[Source: annual_report.pdf, Page 12, Chunk 47]\nQ3 2024 revenue reached $124M...\n\n---\n\n[Source: annual_report.pdf, Page 13, Chunk 52]\nGross margin expanded to 72%...",
  "citations": [
    {
      "position": 1,
      "document_id": "a1b2c3d4-...",
      "original_filename": "annual_report.pdf",
      "chunk_index": 47,
      "page_number": 12,
      "similarity_score": 0.9312
    }
  ],
  "retrieval_metadata": {
    "total_latency_ms": 312.5,
    "embedding_ms": 198.3,
    "search_ms": 4.7,
    "chunks_returned": 5
  }
}
```

---

## 6. Scoped Search (within specific documents)

```bash
curl -X POST http://localhost:8000/api/v1/retrieval/search \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What are the risk factors?",
    "document_ids": ["a1b2c3d4-...", "b2c3d4e5-..."],
    "top_k": 8,
    "similarity_threshold": 0.65
  }'
```

---

## 7. Re-index a Document (force)

```bash
curl -X POST \
  "http://localhost:8000/api/v1/documents/process/a1b2c3d4-...?force=true" \
  -H "Authorization: Bearer $TOKEN"
```

---

## Error Responses

| Status | Meaning |
|--------|---------|
| `401` | Missing or invalid access token |
| `403` | Document belongs to a different user |
| `404` | Document not found |
| `422` | Validation error (e.g., query too long, top_k > 20) |
| `500` | Internal error (check document status for processing failures) |

---

## Status Flow

```
pending  →  processing  →  ready
                      ↘  failed
```

- `pending`:    Uploaded but not yet indexed.
- `processing`: Celery worker is running parse → chunk → embed → store.
- `ready`:      Chunks stored in pgvector, available for retrieval.
- `failed`:     Processing error — see `error_message` field on the document.
