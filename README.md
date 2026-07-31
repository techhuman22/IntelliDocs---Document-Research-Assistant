# 📚 IntelliDocs — Multi-Agent Document Research Assistant

> **Upload documents → Ask questions → Get summaries, quizzes, and flashcards — all grounded in your content with citations.**
> A production-grade full-stack RAG (Retrieval-Augmented Generation) platform built with a multi-agent LangGraph pipeline.

![Next.js](https://img.shields.io/badge/Next.js-15-black?logo=next.js)
![FastAPI](https://img.shields.io/badge/FastAPI-async-009688?logo=fastapi)
![Postgres](https://img.shields.io/badge/PostgreSQL-pgvector-336791?logo=postgresql)
![LangGraph](https://img.shields.io/badge/LangGraph-multi--agent-orange)
![Docker](https://img.shields.io/badge/Docker-compose-2496ED?logo=docker)
![License](https://img.shields.io/badge/license-MIT-blue)

---

## 📑 Table of Contents

1. [Overview](#overview)
2. [Features](#features)
3. [Tech Stack](#tech-stack)
4. [System Architecture](#system-architecture)
5. [The Multi-Agent Pipeline](#the-multi-agent-pipeline)
6. [How RAG Works](#how-rag-works)
7. [Database Schema](#database-schema)
8. [Folder Structure](#folder-structure)
9. [Important Files & What They Do](#important-files--what-they-do)
10. [Authentication Flow](#authentication-flow)
11. [API Endpoints](#api-endpoints)
12. [Local Setup](#local-setup)
13. [Environment Variables](#environment-variables)
14. [Interview Cheat Sheet](#interview-cheat-sheet)

---

## Overview

IntelliDocs is a full-stack AI assistant that transforms static documents (PDF, DOCX, TXT) into an interactive research tool. Users:

1. **Upload** documents → backend extracts text, chunks it, embeds each chunk into a 768-dim vector, stores in PostgreSQL via `pgvector`.
2. **Ask** natural-language questions → a router agent classifies intent → retrieval agent fetches the most relevant chunks via cosine-similarity → response agents generate cited answers.
3. **Get** structured outputs: chat answers, document summaries, MCQ quizzes, or active-recall flashcards — all grounded in the uploaded content.

---

## Features

- 💬 **Chat with your documents** — streaming answers with inline citations via Server-Sent Events
- 📄 **Document summaries** — short overview, detailed analysis, key topics, bullet points
- 🎓 **AI quiz generator** — MCQs with explanations, difficulty selector, scoring
- 🃏 **Flashcards** — flippable cards with "Got it / Still learning" tracking
- 📚 **Multi-document RAG** — semantic search over all your uploads
- 🔒 **Secure auth** — JWT dual-token (access + refresh) with silent refresh
- 🌓 **Dark UI** — clean dashboard built with Tailwind + lucide icons

---

## Tech Stack

### Frontend
| Tech | Purpose |
|---|---|
| **Next.js 15** (App Router) | React framework with file-based routing |
| **TypeScript** | Type safety |
| **Tailwind CSS** | Utility-first styling |
| **React Query v5** | Server state caching |
| **Axios** | HTTP client with JWT refresh interceptor |
| **lucide-react** | Icons |
| **react-hot-toast** | Toast notifications |

### Backend
| Tech | Purpose |
|---|---|
| **FastAPI** | Async Python web framework |
| **SQLAlchemy 2.0** (async) | ORM with async support |
| **asyncpg** | Async PostgreSQL driver |
| **Pydantic v2** | Validation + settings |
| **Alembic** | DB migrations |
| **structlog** | Structured JSON logging |
| **python-jose** | JWT |
| **passlib + bcrypt** | Password hashing |

### AI / ML
| Tech | Purpose |
|---|---|
| **LangGraph** | Multi-agent state machine |
| **Groq Llama 3.3 70B** | Main generation model |
| **Groq Llama 3.1 8B** | Cheap router/intent classifier |
| **HuggingFace `all-mpnet-base-v2`** | Local 768-dim embeddings |
| **tiktoken** | BPE tokenizer for chunking |

### Database & Storage
| Tech | Purpose |
|---|---|
| **PostgreSQL 16** | Primary database |
| **pgvector + HNSW** | Vector type + ANN cosine similarity |
| **Redis** | Celery broker (prod) |
| **Local filesystem** | Document storage |

### Document Processing
| Tech | Purpose |
|---|---|
| **pypdf** | PDF text extraction |
| **python-docx** | DOCX text extraction |
| **filetype** | Magic-byte file detection |

### DevOps / Infra
- **Docker** + **docker-compose** — Postgres + Redis containers
- **Celery** + **Redis** — distributed task queue (prod)
- **FastAPI BackgroundTasks** — inline async tasks (dev)

---

## System Architecture

```
┌────────────────┐         ┌──────────────────────────────────────┐
│  Next.js UI    │         │              FastAPI                 │
│ (port 3000)    │  HTTPS  │           (port 8000)                │
│                ├────────►│                                      │
│ - Dashboard    │  JWT    │  ┌────────────────────────────────┐  │
│ - Chat (SSE)   │         │  │ Auth · Documents · RAG · Tools │  │
│ - Documents    │         │  │ Chat · Health   ·  ...         │  │
│ - Summary      │         │  └────────────────────────────────┘  │
│ - Quiz         │         │             │                        │
│ - Flashcards   │         │             ▼                        │
└────────────────┘         │  ┌────────────────────────────────┐  │
                           │  │   LangGraph Workflow           │  │
                           │  │  Router → Retrieval → ...      │  │
                           │  └────────────────────────────────┘  │
                           │             │                        │
                           │     ┌───────┴────────┐               │
                           │     ▼                ▼               │
                           │ ┌────────┐    ┌────────────┐         │
                           │ │ Groq   │    │ HF Embed   │         │
                           │ │ LLM    │    │ (local)    │         │
                           │ └────────┘    └────────────┘         │
                           └─────────────┬────────────────────────┘
                                         ▼
                         ┌─────────────────────────────────┐
                         │ PostgreSQL 16 + pgvector        │
                         │  users · documents · chunks     │
                         │  chat_sessions · messages       │
                         │  HNSW vector index (cosine)     │
                         └─────────────────────────────────┘
```

---

## The Multi-Agent Pipeline

**The heart of the project.** Five specialised agents orchestrated by a LangGraph `StateGraph`.

### Agents

| Agent | Role | Model |
|---|---|---|
| **1. Router** | Classifies intent: `qa` / `summary` / `quiz` | Llama 8B (fast/cheap) |
| **2. Retrieval** | Embeds query → cosine ANN search → builds context | HF embeddings + pgvector |
| **3. Summary** | Generates structured summary from full document | Llama 70B |
| **4. Quiz** | Generates MCQs with explanations | Llama 70B |
| **5. Final Response** | Formats the final cited answer | Llama 70B |

### Workflow Graph

```
START
  ↓
Router (intent classification)
  ↓
Retrieval (semantic search)
  ↓
  ├── intent=summary → Summary Agent
  ├── intent=quiz    → Quiz Agent
  └── intent=qa      → (skip directly)
  ↓
Final Response
  ↓
END
```

### Why Multi-Agent?

- **Separation of concerns** — each agent does one thing well
- **Cost efficiency** — cheap 8B model routes; expensive 70B runs only when needed
- **Streamable** — UI shows real-time progress per agent via SSE
- **Maintainable** — swap/test/extend each agent independently

---

## How RAG Works

### A. Indexing Pipeline (runs once per upload)

```
PDF/DOCX/TXT
    │
    ▼
[DocumentParserService]  ── extracts text via pypdf / python-docx
    │
    ▼
[ChunkingService]        ── splits into ~500-token chunks with 50-token overlap
    │                        (tiktoken cl100k_base for accurate counting)
    ▼
[EmbeddingService]       ── HF all-mpnet-base-v2 → 768-dim float vectors
    │                        Batched (64) for throughput; runs locally
    ▼
[VectorRepository]       ── INSERT INTO document_chunks (content, embedding, ...)
    │
    ▼
HNSW index ────────────  ── cosine distance, m=16, ef_construction=64
```

### B. Query Pipeline (runs on every chat / tool request)

```
User query
    │
    ▼
Embed query ──────────►  same 768-dim vector
    │
    ▼
SQL: SELECT *, embedding <=> :q AS distance
     FROM document_chunks
     WHERE user_id = :uid AND document_id = ANY(:doc_ids)
     ORDER BY distance ASC LIMIT 15;
    │
    ▼
ContextBuilderService    ── joins top chunks with citation headers
    │                        truncates to fit CONTEXT_MAX_TOKENS budget
    ▼
LLM prompt with context  ── grounded answer + [Source N] citations
```

---

## Database Schema

```sql
users
  id (uuid, pk), email (unique), password_hash, full_name,
  is_active, created_at

documents
  id (uuid, pk), user_id (fk→users), original_filename,
  stored_filename, file_type, mime_type, file_size_bytes,
  storage_path, status (pending|processing|ready|failed),
  chunk_count, doc_metadata (jsonb), created_at

document_chunks
  id (uuid, pk), document_id (fk→documents), user_id (denormalized),
  chunk_index (int), content (text), page_number (int),
  embedding (vector(768)),         -- pgvector type
  token_count (int)
  └ INDEX hnsw_idx ON embedding USING hnsw (embedding vector_cosine_ops)
  └ INDEX ix_document_chunks_user_id
  └ UNIQUE (document_id, chunk_index)

chat_sessions
  id (uuid, pk), user_id (fk), title, session_type,
  document_ids (uuid[]),           -- pg array w/ GIN index
  is_archived, created_at, updated_at

chat_messages
  id (uuid, pk), session_id (fk), role (user|assistant|system),
  content, intent, token_count, citations (jsonb), created_at

refresh_tokens
  id (uuid, pk), user_id (fk), token_hash, expires_at,
  is_revoked, created_at
```

**Why denormalize `user_id` onto `document_chunks`?** So the similarity-search query filters on `user_id` directly without joining `documents` — critical when chunks scale to millions of rows.

---

## Folder Structure

```
New AI full project/
├── backend/                          # FastAPI + LangGraph backend
│   ├── app/
│   │   ├── agents/                   # ⭐ LangGraph multi-agent pipeline
│   │   ├── api/v1/                   # REST endpoints
│   │   ├── config/                   # Settings (pydantic-settings)
│   │   ├── core/                     # logging, exceptions, security, middleware
│   │   ├── db/                       # SQLAlchemy models, repos, migrations
│   │   ├── schemas/                  # Pydantic request/response models
│   │   ├── services/                 # Business logic
│   │   ├── workers/                  # Celery tasks + inline dev runner
│   │   └── main.py                   # FastAPI app factory
│   ├── tests/                        # pytest test suites
│   ├── .env.example
│   ├── alembic.ini
│   ├── Dockerfile
│   └── requirements.txt
│
├── frontend/                         # Next.js 15 frontend
│   └── src/
│       ├── app/                      # App Router pages
│       │   ├── (auth)/               # login, register
│       │   ├── (dashboard)/          # protected pages
│       │   ├── layout.tsx
│       │   └── page.tsx              # landing
│       ├── components/               # Reusable UI components
│       ├── contexts/                 # React contexts (Auth)
│       └── lib/                      # API clients, query setup, utils
│
├── docker/postgres/init.sql          # Enables pgvector on first boot
├── docker-compose.yml                # Postgres + Redis + (Celery) services
├── docs/                             # API docs / phase notes
├── .gitignore
└── README.md
```

---

## Important Files & What They Do

This section maps the most important files in the project to what they do — perfect for a code walkthrough in an interview.

### 🧠 Backend — Multi-Agent Pipeline (`backend/app/agents/`)

| File | What It Does |
|---|---|
| **`state.py`** | Defines `AgentState` — a TypedDict that flows through every node. Holds query, user_id, intent, retrieved_chunks, built_context, summary/quiz data, final_response, citations, error. |
| **`workflow.py`** | Wires the LangGraph `StateGraph`: sets the entry point (Router), adds conditional edges based on intent, connects all nodes to FinalResponse → END. |
| **`router_agent.py`** | Classifies the user query into `qa` / `summary` / `quiz` using the cheap Llama 8B model. Sets `state["intent"]`. |
| **`retrieval_agent.py`** | Embeds the query via HF, runs cosine ANN search via VectorRepository, builds context string with citation headers. Sets `state["retrieved_chunks"]` and `state["built_context"]`. |
| **`summary_agent.py`** | When intent=summary, calls Llama 70B with `.with_structured_output(SummarySchema)` → returns short summary, detailed summary, bullet points, key topics. |
| **`quiz_agent.py`** | When intent=quiz, generates MCQs with options, correct answer, and explanation via structured LLM output. |
| **`final_response_agent.py`** | Formats the final user-facing message. For `qa`: writes a conversational cited answer. For `summary`/`quiz`: marshals structured data into the chat reply. |
| **`prompts.py`** | All LLM prompt templates (system + human). Important: escaped braces (`{{...}}`) to avoid `.format()` collisions with JSON examples. |

### 🛣️ Backend — API Routes (`backend/app/api/v1/`)

| File | What It Does |
|---|---|
| **`router.py`** | The root v1 router. Mounts all sub-routers (auth, users, documents, rag, chat, tools, health). |
| **`auth.py`** | `POST /auth/register`, `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`. Issues JWT pairs, handles refresh rotation. |
| **`documents.py`** | `POST /documents/upload` (auto-triggers processing), `GET /documents` (list), `POST /documents/process/{id}` (manual re-process), `DELETE /documents/{id}`. |
| **`chat.py`** | `POST /chat/stream` — Server-Sent Events endpoint. Streams agent events (`agent_start`, `agent_end`, `final`) so UI shows progress. Manages chat sessions. |
| **`rag.py`** | `POST /rag/search` — raw semantic search endpoint (returns chunks without LLM). Useful for debugging retrieval quality. |
| **`tools.py`** | ⭐ `POST /tools/summary`, `/tools/quiz`, `/tools/flashcards`. **Bypasses similarity search** — fetches ALL chunks for selected documents directly via SQL, so the LLM sees the full content. |
| **`users.py`** | `GET /users/me` — returns current user info. |
| **`health.py`** | `GET /health` — liveness probe. |

### 🔌 Backend — Dependencies (`backend/app/api/dependencies.py`)
Factory functions used by FastAPI's `Depends()`:
- `get_current_active_user` — extracts user from JWT
- `get_db` — yields async SQLAlchemy session
- `get_document_service`, `get_storage_service`, `get_embedding_service`, etc.

### 🛠️ Backend — Services (`backend/app/services/`)

| File | What It Does |
|---|---|
| **`document_service.py`** | High-level document lifecycle: upload, list, get, delete. Compensating transactions if DB write fails after disk save. |
| **`document_processing_service.py`** | ⭐ Orchestrates parse → chunk → embed → store. Updates `documents.status` through the pipeline. |
| **`document_parser_service.py`** | Extracts text from PDF (pypdf), DOCX (python-docx), or TXT. |
| **`chunking_service.py`** | Splits text into ~500-token windows with 50-token overlap using tiktoken `cl100k_base`. Tracks page numbers. |
| **`embedding_service.py`** | Loads HF `all-mpnet-base-v2` once at startup. `embed_documents(texts)` returns 768-dim float vectors in batches of 64. |
| **`retrieval_service.py`** | Wraps the vector repository — embeds query, performs cosine search, returns `RetrievedChunk` objects. |
| **`context_builder_service.py`** | Joins retrieved chunks with `[Source N: filename, Page X]` headers, respects `CONTEXT_MAX_TOKENS` budget, computes sufficiency score. |
| **`chat_service.py`** | Manages chat sessions, persists user/assistant messages, streams the LangGraph workflow. |
| **`storage_service.py`** | Saves uploaded files to disk, validates magic bytes + size, deletes orphans. |
| **`auth_service.py`** | Register/login logic. Hashes passwords. Issues + rotates JWT pairs. |
| **`user_service.py`** | Get/update current user. |

### 💾 Backend — Database Layer (`backend/app/db/`)

| File | What It Does |
|---|---|
| **`base.py`** | Defines `AsyncEngine`, `AsyncSessionLocal`, the `get_db` dependency, and DB init/shutdown hooks. |
| **`models.py`** | ⭐ All SQLAlchemy ORM models: `User`, `Document`, `DocumentChunk` (with `Vector(768)`), `ChatSession`, `ChatMessage`, `RefreshToken`. |
| **`repositories/base.py`** | Generic CRUD operations (create, get, update, delete) using SQLAlchemy 2.0 style. |
| **`repositories/vector_repository.py`** | ⭐ The actual similarity search SQL. Uses `type_coerce(Float)` to fix the pgvector + SQLAlchemy type adapter bug. |
| **`repositories/document_repository.py`** | Document queries (by id, by user, count, storage size). |
| **`repositories/user_repository.py`** | User CRUD. |
| **`repositories/token_repository.py`** | Refresh token storage + revocation. |
| **`repositories/chat_repository.py`** | Chat session + message CRUD. |
| **`migrations/versions/*.py`** | Alembic migration files (initial schema, HNSW index, refresh tokens, etc.). |

### ⚙️ Backend — Core & Config (`backend/app/core/`, `config/`)

| File | What It Does |
|---|---|
| **`config/settings.py`** | Pydantic-settings model. Loads from `.env`. Fields: DATABASE_URL, GROQ_API_KEY, JWT secrets, CORS origins, chunk sizes, etc. |
| **`core/security.py`** | JWT encode/decode, password hashing/verification, secure random token generation. |
| **`core/exceptions.py`** | Custom exception classes (DocumentNotFoundException, UnauthorizedException, ValidationException, etc.) with HTTP status codes. |
| **`core/middleware.py`** | Request logging middleware — generates `request_id`, logs method/path/duration/status. |
| **`core/logging.py`** | Configures structlog for structured JSON logs. |

### 🏃 Backend — Workers (`backend/app/workers/`)

| File | What It Does |
|---|---|
| **`celery_app.py`** | Celery app instance + broker config (for production async workers). |
| **`tasks.py`** | `process_document` (Celery task) + `run_document_processing_inline` (dev mode without Celery — runs the same pipeline directly in a background task). |

### 🚀 Backend — Entrypoint

| File | What It Does |
|---|---|
| **`main.py`** | FastAPI app factory. Adds CORS middleware, exception handlers, request logging middleware, lifespan events (load embedding model at startup, dispose engine on shutdown). |

---

### 🎨 Frontend — Pages (`frontend/src/app/`)

| File | What It Does |
|---|---|
| **`layout.tsx`** | Root layout. Sets metadata, fonts, wraps everything in `<Providers>` (React Query + AuthProvider). |
| **`page.tsx`** | Landing page (hero, features, footer). |
| **`(auth)/login/page.tsx`** | Login form with react-hook-form, calls `/auth/login`, stores tokens. |
| **`(auth)/register/page.tsx`** | Registration form. |
| **`(dashboard)/layout.tsx`** | Protected layout with Sidebar + content area. Wraps children in `<ProtectedRoute>`. |
| **`(dashboard)/dashboard/page.tsx`** | Dashboard with stat cards (docs count, chats count) + recent items. |
| **`(dashboard)/documents/page.tsx`** | ⭐ Document upload (drag-drop) + grid view with status badges. Calls `/documents/upload` (auto-processes). |
| **`(dashboard)/chat/page.tsx`** | ⭐ Streaming chat UI. Parses SSE events, shows agent progress, renders messages with citations. |
| **`(dashboard)/summary/page.tsx`** | Document picker → calls `/tools/summary` → renders short/detailed summary + topics + bullets. |
| **`(dashboard)/quiz/page.tsx`** | Document picker + difficulty/count → calls `/tools/quiz` → interactive MCQ with scoring. |
| **`(dashboard)/flashcards/page.tsx`** | Document picker → calls `/tools/flashcards` → flippable cards with "Got it"/"Still learning" tracking. |
| **`(dashboard)/history/page.tsx`** | Past chat sessions. Resume / archive / delete. |
| **`(dashboard)/profile/page.tsx`** | Current user info. |

### 🧩 Frontend — Components (`frontend/src/components/`)

| File | What It Does |
|---|---|
| **`Providers.tsx`** | Wraps app in `QueryClientProvider`, `AuthProvider`, and ReactQueryDevtools (dev only). |
| **`auth/ProtectedRoute.tsx`** | Redirects to /login if no token; shows loader while auth state hydrates. |
| **`layout/Sidebar.tsx`** | Left nav with links to all dashboard pages. |
| **`layout/Navbar.tsx`** | Top navbar on landing page. |
| **`chat/ChatInput.tsx`** | Message input box with send button. |
| **`chat/ChatMessage.tsx`** | Renders a single user/assistant message bubble with markdown + citations. |
| **`chat/ChatSidebar.tsx`** | Lists chat sessions with delete buttons. |
| **`chat/AgentActivityPanel.tsx`** | Shows live agent progress (Router → Retrieval → ...) during streaming. |
| **`documents/UploadArea.tsx`** | react-dropzone drag-drop upload area with progress. |
| **`documents/DocumentCard.tsx`** | Document tile with status badge + delete + reprocess buttons. |
| **`dashboard/DashboardCard.tsx`** | Stat card component for the dashboard. |
| **`common/LoadingSpinner.tsx`** | Loader + ThinkingDots animation. |

### 🔌 Frontend — API Clients (`frontend/src/lib/api/`)

| File | What It Does |
|---|---|
| **`axios.ts`** | ⭐ Axios instance with request interceptor (attaches Bearer token) + response interceptor (silent token refresh on 401, then retry). |
| **`auth.ts`** | `login()`, `register()`, `getMe()`, `logout()`. |
| **`documents.ts`** | `upload()` (with progress), `list()`, `get()`, `delete()`, `triggerProcessing()`, `getStorageStats()`. |
| **`chat.ts`** | `streamChat()` — async generator that consumes SSE response and yields parsed events. |
| **`tools.ts`** | `summary()`, `quiz()`, `flashcards()`. 2-min timeout because LLM structured output is slow. |

### 🗂️ Frontend — Other

| File | What It Does |
|---|---|
| **`lib/queryClient.ts`** | React Query client config + centralised `queryKeys` factory (shared cache keys across components). |
| **`lib/utils.ts`** | Helpers: `cn()` (Tailwind class merger), `formatBytes()`, `getStatusColor()`, etc. |
| **`contexts/AuthContext.tsx`** | React Context that holds the current user. Auto-fetches `/users/me` on mount if token exists. |
| **`types/*.ts`** | TypeScript types for User, Document, ChatMessage, etc. |
| **`app/globals.css`** | Tailwind directives, CSS variables for theming, custom utility classes. |
| **`tailwind.config.ts`** | Tailwind theme extension (colors, animations). |

---

## Authentication Flow

- **Dual-token JWT**: short-lived access (15 min) + long-lived refresh (7 days)
- **Refresh tokens hashed in DB** — single UPDATE to revoke
- **Frontend axios interceptor**: catches 401 → calls `/auth/refresh` → retries the original request silently. User only sees logout if refresh also fails.
- **Passwords**: bcrypt-hashed with per-user salt (12 rounds)

```
POST /auth/register → returns access + refresh tokens
POST /auth/login    → returns access + refresh tokens
POST /auth/refresh  → returns new pair (rotation)
POST /auth/logout   → revokes the refresh token in DB
```

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/auth/register` | Create account |
| `POST` | `/api/v1/auth/login` | Login (returns tokens) |
| `POST` | `/api/v1/auth/refresh` | Refresh access token |
| `POST` | `/api/v1/auth/logout` | Logout |
| `GET` | `/api/v1/users/me` | Current user info |
| `POST` | `/api/v1/documents/upload` | Upload document (auto-processes) |
| `GET` | `/api/v1/documents` | List documents |
| `POST` | `/api/v1/documents/process/{id}` | Manually trigger processing |
| `DELETE` | `/api/v1/documents/{id}` | Delete document |
| `POST` | `/api/v1/rag/search` | Raw semantic search |
| `POST` | `/api/v1/chat/stream` | SSE-streaming chat |
| `GET` | `/api/v1/sessions` | List chat sessions |
| `POST` | `/api/v1/tools/summary` | Generate summary |
| `POST` | `/api/v1/tools/quiz` | Generate quiz |
| `POST` | `/api/v1/tools/flashcards` | Generate flashcards |
| `GET` | `/api/v1/health` | Health check |

Interactive docs at `http://localhost:8000/docs` (Swagger UI).

---

## Local Setup

### Prerequisites
- Python 3.11+ · Node 20+ · Docker Desktop · Groq API key (free at [console.groq.com](https://console.groq.com))

### 1. Start Postgres + Redis
```bash
docker compose up -d postgres redis
```

### 2. Backend
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate           # Windows
# source .venv/bin/activate      # macOS/Linux

pip install -r requirements.txt

# Copy and edit .env
cp .env.example .env
# Set GROQ_API_KEY and SECRET_KEY

alembic upgrade head
python -m uvicorn app.main:app --reload --port 8000
```

### 3. Frontend
```bash
cd frontend
npm install
npm run dev -- --port 3000
```

Open **http://localhost:3000** → register → upload a PDF → wait for `ready` → chat / summarize / quiz / flashcards.

---

## Environment Variables

| Variable | Description |
|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@host:5432/db` |
| `GROQ_API_KEY` | From console.groq.com |
| `GROQ_MODEL` | Main LLM (default `llama-3.3-70b-versatile`) |
| `GROQ_ROUTER_MODEL` | Router LLM (default `llama-3.1-8b-instant`) |
| `SECRET_KEY` | 32-byte hex string for JWT signing |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Default 15 |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Default 7 |
| `CORS_ORIGINS` | Comma-separated frontend URLs |
| `EMBEDDING_MODEL` | HF model id (default `sentence-transformers/all-mpnet-base-v2`) |
| `CHUNK_SIZE` | Tokens per chunk (default 500) |
| `CHUNK_OVERLAP` | Token overlap (default 50) |
| `CONTEXT_MAX_TOKENS` | Max tokens in retrieval context (default 4000) |
| `MAX_UPLOAD_SIZE_MB` | Default 50 |
| `REDIS_URL` | For Celery in prod |

---

## Interview Cheat Sheet

### Q: What is RAG?
Retrieval-Augmented Generation. Instead of relying solely on the LLM's training data, we (a) retrieve relevant documents from a vector DB using semantic similarity, (b) inject them into the prompt as context, and (c) let the LLM generate a grounded, cite-able answer. Reduces hallucinations and lets the model talk about private/recent data.

### Q: Why a vector database instead of keyword search?
Embeddings capture **semantic similarity** — a query like *"how do neural nets learn?"* matches *"backpropagation and gradient descent"* even with no shared keywords. We use cosine distance with pgvector's HNSW index — O(log N) approximate nearest-neighbour search.

### Q: Why HNSW over IVFFlat?
HNSW gives better recall at high QPS and doesn't need a pre-training step. IVFFlat needs pre-clustering and rebuilding when data grows.

### Q: Why local embeddings (HF) instead of an API?
Privacy (documents never leave the server), zero per-token cost, low latency. `all-mpnet-base-v2` is a strong general-purpose 768-dim sentence embedder.

### Q: LangGraph vs LangChain?
LangChain composes things linearly (Chain → Chain). LangGraph models the flow as a **stateful directed graph** — supports loops, conditional branches, parallel nodes, checkpointing, and human-in-the-loop. Better fit for multi-agent systems where the path depends on intent.

### Q: Why 5 agents instead of one big prompt?
Separation of concerns. The router runs a cheap 8B model. The 70B model only runs for the final generation. Each agent is independently testable. Streaming is cleaner — UI shows per-agent progress.

### Q: How does the chat stream tokens?
**Server-Sent Events** (`text/event-stream`). FastAPI yields JSON events with `{event_type: "agent_start" | "agent_end" | "final"}`. The browser uses `fetch` + a `ReadableStream` reader — simpler than WebSockets for one-way push.

### Q: How is authentication secure?
- Passwords hashed with bcrypt (12 rounds, per-user salt).
- Short-lived JWT access token (15 min) signed with HS256.
- Refresh token (7 days) hashed in DB — revocation = single UPDATE.
- Frontend uses axios interceptor for silent refresh on 401.

### Q: How does chunking work?
Text → tiktoken `cl100k_base` tokenizer → split into `CHUNK_SIZE` (500) token windows with `CHUNK_OVERLAP` (50) — context isn't lost at chunk boundaries. Each chunk stores `chunk_index` and (for PDFs) `page_number`.

### Q: How would you scale this?
- Replace BackgroundTasks with Celery + Redis (already wired).
- Read-replica for vector queries; tune HNSW params.
- Stream tokens directly from Groq instead of waiting for full response.
- Cache embeddings for repeated queries (Redis TTL).
- Shard chunks table by `user_id` at scale.
- Add a re-ranker (Cohere Rerank or cross-encoder) over top-K chunks.

### Q: Tricky bugs you fixed?
1. **pgvector type adapter** — `<=>` operator returns a float, but SQLAlchemy inherited the Vector type and tried to parse the float as a vector string → `'float' is not subscriptable`. Fix: `type_coerce(..., Float)` to coerce the result type.
2. **Upload race condition** — FastAPI `BackgroundTasks` ran before the DB transaction committed → worker queried for a document that didn't exist yet. Fix: explicit `await db.commit()` in the upload route before scheduling the task.

### Q: How would you evaluate the system?
- **Retrieval quality**: recall@k on a labelled QA dataset.
- **Answer faithfulness**: ratio of answer claims supported by retrieved chunks (LLM-as-judge).
- **Latency**: P50/P95 per agent node + end-to-end.
- **Token cost** per query (input + output).
- **Human ratings** for summary coherence + quiz difficulty calibration.

---

## 📜 License

MIT — built as a learning project.

## 🙏 Acknowledgements

Built with [Next.js](https://nextjs.org), [FastAPI](https://fastapi.tiangolo.com), [LangGraph](https://github.com/langchain-ai/langgraph), [pgvector](https://github.com/pgvector/pgvector), [Groq](https://groq.com), and [HuggingFace](https://huggingface.co).
