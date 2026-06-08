# IntelliDocs

> Multi-agent AI research assistant. Upload documents, ask questions, get summaries, quizzes, and flashcards — all grounded in your content with citations.

![Next.js](https://img.shields.io/badge/Next.js-15-black?logo=next.js)
![FastAPI](https://img.shields.io/badge/FastAPI-async-009688?logo=fastapi)
![Postgres](https://img.shields.io/badge/PostgreSQL-pgvector-336791?logo=postgresql)
![LangGraph](https://img.shields.io/badge/LangGraph-multi--agent-orange)
![License](https://img.shields.io/badge/license-MIT-blue)

---

## ✨ Features

- 💬 **Chat with your documents** — streaming answers with inline citations
- 📄 **Document summaries** — short overview, detailed analysis, key topics, bullet points
- 🎓 **AI quiz generator** — MCQs with explanations, difficulty selector, scoring
- 🃏 **Flashcards** — flippable cards for active recall study
- 📚 **Multi-document RAG** — semantic search over all your uploads via pgvector
- 🔒 **Secure auth** — JWT dual-token with silent refresh
- 🌓 **Dark UI** — clean dashboard built with Tailwind + lucide icons

## 🏗️ Tech Stack

**Frontend** — Next.js 15 (App Router) · TypeScript · Tailwind CSS · React Query
**Backend** — FastAPI · SQLAlchemy 2.0 (async) · Pydantic v2
**AI** — Groq Llama 3.3 70B · HuggingFace all-mpnet-base-v2 (local embeddings) · LangGraph
**Data** — PostgreSQL 16 + pgvector (HNSW index, cosine similarity)
**Auth** — JWT (access + refresh) · bcrypt

## 🤖 How It Works

```
Upload PDF/DOCX/TXT → parse → chunk (500 tokens, 50 overlap)
                                  ↓
                        embed (768-dim, HF mpnet)
                                  ↓
                        store in pgvector (HNSW)

User query → router agent → retrieval agent → summary / quiz / qa agent → response
            (Llama 8B)     (cosine search)          (Llama 70B)
```

A **LangGraph state machine** orchestrates five specialised agents:

| Agent | Role |
|---|---|
| Router | Classifies intent: `qa` / `summary` / `quiz` (cheap 8B model) |
| Retrieval | Embeds query, runs cosine ANN search, builds context |
| Summary | Generates structured summaries from full document content |
| Quiz | Generates MCQs with explanations and scoring |
| Final Response | Formats the final cited answer |

## 🚀 Quick Start

### Prerequisites
- Python 3.11+ · Node 20+ · Docker (for Postgres)

### 1. Start Postgres + Redis
```bash
docker compose up -d
```

### 2. Backend
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux
pip install -r requirements.txt

# create .env (see backend/.env.example)
cp .env.example .env
# Set GROQ_API_KEY, SECRET_KEY, DATABASE_URL

alembic upgrade head
python -m uvicorn app.main:app --reload --port 8000
```

### 3. Frontend
```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:3000** → register → upload a document → start chatting.

## 📁 Project Structure

```
.
├── backend/
│   ├── app/
│   │   ├── agents/         # LangGraph multi-agent pipeline
│   │   ├── api/v1/         # FastAPI routes
│   │   ├── services/       # business logic (parsing, embedding, retrieval)
│   │   ├── db/             # SQLAlchemy models, repositories, migrations
│   │   └── main.py
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── app/            # Next.js App Router pages
│       ├── components/
│       └── lib/api/        # axios clients
├── docker-compose.yml      # Postgres (pgvector) + Redis
└── README.md
```

## 📸 Screenshots

<!-- Add screenshots here -->
> _Dashboard · Document upload · Streaming chat · Quiz generator · Flashcards_

## 🛠️ Configuration

Key environment variables (`backend/.env`):

| Variable | Description |
|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@host:5432/db` |
| `GROQ_API_KEY` | Get one free at [console.groq.com](https://console.groq.com) |
| `SECRET_KEY` | 32-byte hex for JWT signing |
| `CORS_ORIGINS` | Comma-separated frontend URLs |
| `CHUNK_SIZE` | Tokens per chunk (default 500) |
| `CHUNK_OVERLAP` | Token overlap between chunks (default 50) |

## 📜 License

MIT — free to use, modify, and distribute.

## 🙏 Acknowledgements

Built with the open-source tooling of [Next.js](https://nextjs.org), [FastAPI](https://fastapi.tiangolo.com), [LangGraph](https://github.com/langchain-ai/langgraph), [pgvector](https://github.com/pgvector/pgvector), [Groq](https://groq.com), and [HuggingFace](https://huggingface.co).
