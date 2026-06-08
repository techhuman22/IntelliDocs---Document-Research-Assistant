# Multi-Agent Chat API Examples

All endpoints require: `Authorization: Bearer <access_token>`

---

## 1. QA Intent — "What is CNN?"

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is a Convolutional Neural Network?",
    "document_ids": []
  }'
```

**Response**
```json
{
  "session_id": "a1b2c3d4-...",
  "message_id": "m1m2m3m4-...",
  "query": "What is a Convolutional Neural Network?",
  "intent": "qa",
  "response": "A Convolutional Neural Network (CNN) is a deep learning architecture designed for processing structured grid data like images...\n\n[Source 1] describes how CNNs use learnable filters that slide across the input to detect features...",
  "structured_data": null,
  "citations": [
    {
      "position": 1,
      "document_id": "doc-uuid-...",
      "original_filename": "deep_learning_notes.pdf",
      "page_number": 14,
      "chunk_index": 47,
      "similarity_score": 0.931
    }
  ],
  "agent_trace": [
    {"agent_name": "router",         "status": "success", "latency_ms": 312},
    {"agent_name": "retrieval",      "status": "success", "latency_ms": 189},
    {"agent_name": "final_response", "status": "success", "latency_ms": 876}
  ],
  "latency_ms": 1421
}
```

---

## 2. Summary Intent — "Summarize this paper"

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Summarize the main findings of this research paper",
    "document_ids": ["doc-uuid-..."]
  }'
```

**Response**
```json
{
  "intent": "summary",
  "response": "## Summary\n\nThis paper presents a novel approach to...\n\n### Key Takeaways\n- Finding 1...",
  "structured_data": {
    "short_summary": "This research presents a transformer-based architecture...",
    "detailed_summary": "The paper introduces a new attention mechanism that...",
    "bullet_points": [
      "Achieves 43% improvement over baseline on GLUE benchmark",
      "Reduces training time by 60% using sparse attention"
    ],
    "key_topics": ["transformers", "attention mechanism", "NLP benchmarks"],
    "word_count": 342
  },
  "agent_trace": [
    {"agent_name": "router",         "status": "success", "latency_ms": 298},
    {"agent_name": "retrieval",      "status": "success", "latency_ms": 234},
    {"agent_name": "summary",        "status": "success", "latency_ms": 1823},
    {"agent_name": "final_response", "status": "success", "latency_ms": 12}
  ],
  "latency_ms": 2401
}
```

---

## 3. Quiz Intent — "Create 5 MCQ questions"

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Create 5 medium-difficulty MCQ questions about backpropagation",
    "document_ids": ["doc-uuid-..."]
  }'
```

**Response**
```json
{
  "intent": "quiz",
  "response": "## Quiz: Backpropagation\n\n**Question 1** (Medium)\nWhat does the chain rule compute in backpropagation?\n  A) The forward pass activations  \n  B) Gradients of the loss with respect to each weight ✓\n  C) The learning rate schedule\n  D) Batch normalization factors\n\n*Explanation:* The chain rule allows computing partial derivatives...",
  "structured_data": {
    "topic": "Backpropagation",
    "difficulty": "medium",
    "total_questions": 5,
    "questions": [
      {
        "question_number": 1,
        "question_type": "mcq",
        "difficulty": "medium",
        "question": "What does the chain rule compute in backpropagation?",
        "options": [
          {"label": "A", "text": "The forward pass activations", "is_correct": false},
          {"label": "B", "text": "Gradients of the loss with respect to each weight", "is_correct": true},
          {"label": "C", "text": "The learning rate schedule", "is_correct": false},
          {"label": "D", "text": "Batch normalization factors", "is_correct": false}
        ],
        "answer": "B",
        "explanation": "The chain rule allows computing partial derivatives of the loss..."
      }
    ]
  }
}
```

---

## 4. Multi-turn conversation

```bash
# Turn 1
curl -X POST http://localhost:8000/api/v1/chat \
  -d '{"query": "What is gradient descent?"}' \
  # Returns: {"session_id": "sess-abc-...", "response": "..."}

# Turn 2 — continue in same session
curl -X POST http://localhost:8000/api/v1/chat \
  -d '{
    "query": "How does it compare to Adam optimizer?",
    "session_id": "sess-abc-..."
  }'
```

---

## 5. Streaming

```bash
curl -X POST http://localhost:8000/api/v1/chat/stream \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{"query": "Summarize the transformer paper"}' \
  --no-buffer
```

**Stream output**
```
data: {"event_type": "agent_end", "data": {"agent": "router", "status": "success", "latency_ms": 310}}

data: {"event_type": "agent_end", "data": {"agent": "retrieval", "status": "success", "latency_ms": 198}}

data: {"event_type": "agent_end", "data": {"agent": "summary", "status": "success", "latency_ms": 1892}}

data: {"event_type": "agent_end", "data": {"agent": "final_response", "status": "success", "latency_ms": 11}}

data: {"event_type": "final", "data": {"session_id": "...", "intent": "summary", "response": "## Summary\n..."}}
```

---

## 6. Session management

```bash
# List sessions
curl http://localhost:8000/api/v1/sessions \
  -H "Authorization: Bearer $TOKEN"

# Get session messages
curl http://localhost:8000/api/v1/sessions/sess-abc-.../messages \
  -H "Authorization: Bearer $TOKEN"

# Archive a session
curl -X DELETE http://localhost:8000/api/v1/sessions/sess-abc-... \
  -H "Authorization: Bearer $TOKEN"
```

---

## Workflow diagram

```
User Query
    │
    ▼
[Router Agent]
    │  intent: "qa" | "summary" | "quiz"
    ▼
[Retrieval Agent]  ← pgvector cosine similarity
    │
    ├─ "qa"      ──────────────────────────────────▶ [Final Response]
    ├─ "summary" ──▶ [Summary Agent] ─────────────▶ [Final Response]
    └─ "quiz"    ──────────▶ [Quiz Agent] ─────────▶ [Final Response]
                                                           │
                                                          API
```

---

## Error responses

| Status | Cause |
|--------|-------|
| `401` | Missing or expired access token |
| `404` | Session not found or not owned by user |
| `422` | Validation error (empty query, query > 4000 chars) |
| `200` with `error` field | Partial pipeline failure (response still returned) |
