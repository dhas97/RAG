# AI Document Assistant — Advanced RAG

A production-grade **Retrieval-Augmented Generation (RAG)** application. Upload PDF or TXT documents, ask questions in plain English, and get grounded answers with inline citations showing exactly which page and passage the answer came from.

---

## Architecture

```
┌──────────────────┐   HTTP   ┌──────────────────────────────────────────────┐
│   React (Vite)   │◄────────►│              Django REST API                  │
│  - Chat UI       │          │  POST /api/chat/          → answer+citations  │
│  - Doc upload    │          │  GET  /api/documents/     → list docs         │
│  - Progress bar  │          │  POST /api/documents/upload/ → 202 + id      │
│  - Citation cards│          │  GET  /api/documents/<id>/status/ → progress  │
│  - Eval badges   │          │  DELETE /api/documents/<id>/ → delete        │
└──────────────────┘          └─────────────────┬────────────────────────────┘
                                                 │
                    ┌────────────────────────────▼─────────────────────────────┐
                    │                  Advanced RAG Pipeline                    │
                    │                                                           │
                    │  Query         BM25 ──────────────────┐                  │
                    │  Transform ──► pgvector HNSW × 4 ─────┼──► RRF Fusion   │
                    │  (HyDE,        (multi-query,           │         │        │
                    │   rewrite,      HyDE embed)            │         ▼        │
                    │   multi-query)                         │    LLM Rerank   │
                    │                                        │         │        │
                    │                                        │         ▼        │
                    │                                        │    Generate +    │
                    │                                        │    Citations     │
                    └────────────────────────────────────────┴─────────────────┘
                                                 │
                    ┌────────────────────────────▼─────────────────────────────┐
                    │         PostgreSQL + pgvector                             │
                    │  api_document       — metadata + status + progress       │
                    │  api_documentchunk  — text │ parent_text │ vector(768)   │
                    │                            │ page_number │ HNSW index    │
                    └────────────────────────────┬─────────────────────────────┘
                                                 │
                    ┌────────────────────────────▼─────────────────────────────┐
                    │         Redis + Celery Worker                             │
                    │  Redis  — message broker (queues ingestion jobs)         │
                    │  Celery — background worker: chunks → embeds → saves     │
                    │           updates chunks_done every 50 chunks            │
                    └──────────────────────────────────────────────────────────┘
```

---

## Upload Flow (Async — returns in ~1 second)

```
Browser → POST /api/documents/upload/
              ↓ ~1 second
          202 Accepted { id: 42, status: "pending" }
              ↓
          Job pushed to Redis ──► Celery worker picks it up
                                        ↓
                               chunks PDF with NLTK
                               for each chunk → Gemini embed → save
                               updates chunks_done every 50 chunks
                               pauses 60s every 80 chunks (rate limit)
                                        ↓
                               status = "done"

Browser polls GET /api/documents/42/status/ every 2s
  → shows live progress bar: "350 / 2050 chunks embedded"
  → stops when status = "done", document list refreshes
```

## Chat Flow

```
Browser → POST /api/chat/ { question, top_k, evaluate }
              ↓
   [1] query_processor.py
       rewrite_query()         → cleaner, self-contained query
       generate_multi_queries() → 2 alternative phrasings
       generate_hyde_passage()  → hypothetical answer passage
       → 4 query strings total
              ↓
   [2] retrieval.py
       BM25 keyword search over all child chunks
       pgvector ANN cosine search × 4 (one per query variant)
       RRF fusion of all 5 ranked lists → top_k × 3 candidates
              ↓
   [3] reranking.py
       Gemini scores all candidates 1–10 in one call → top_k chunks
              ↓
   [4] llm.py
       Numbered passages [1][2]... sent to Gemini 2.5 Flash
       → { answer with inline citations, citations list }
              ↓
   [5] (optional) evaluation.py
       faithfulness / answer relevancy / context relevancy scores
              ↓
   { answer, citations, sources_used, evaluation? }
```

---

## Advanced RAG Features

| Feature | What it does |
|---|---|
| **Semantic chunking** | NLTK sentence-aware splits — no mid-sentence cuts |
| **Parent-child hierarchy** | Small child chunk retrieved, wide parent chunk sent to LLM |
| **Task-type embeddings** | `RETRIEVAL_DOCUMENT` at index time, `RETRIEVAL_QUERY` at query time |
| **Query rewriting** | Gemini rewrites ambiguous queries before retrieval |
| **Multi-query generation** | 2 alternative phrasings to cover different vocabulary |
| **HyDE** | Hypothetical Document Embedding — embeds a fake answer, not the question |
| **Hybrid search** | BM25 (keyword) + pgvector ANN (semantic) run in parallel |
| **RRF fusion** | Reciprocal Rank Fusion merges all ranked lists — no score normalisation needed |
| **LLM reranking** | Gemini scores all candidates 1–10 in one call, keeps top-k |
| **Structured citations** | Inline `[1][2]` markers + expandable source cards with page numbers |
| **RAG evaluation** | Faithfulness, Answer Relevancy, Context Relevancy (opt-in) |
| **pgvector HNSW** | O(log n) approximate nearest-neighbour — production-scale vector search |
| **Async ingestion** | Celery + Redis — upload returns 202 in ~1s, embedding runs in background |
| **Live progress bar** | Frontend polls `/status/` every 2s, shows chunks_done / chunks_total |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 18 + Vite |
| Backend | Django 4.2 + Django REST Framework |
| LLM | Google Gemini 2.5 Flash |
| Embeddings | Google Gemini `gemini-embedding-001` (768-dim, task-typed) |
| Vector store | PostgreSQL 16 + pgvector (HNSW index) |
| Keyword search | rank-bm25 |
| Chunking | NLTK sentence tokenisation + parent-child windows |
| PDF parsing | pdfplumber |
| Task queue | Celery 5.3 |
| Message broker | Redis 7 |
| Container | Docker + Docker Compose |

---

## File-by-File Guide

Every file in the project — what it is, why it exists.

---

### Root

| File | What it is | Why it exists |
|---|---|---|
| `docker-compose.yml` | Defines 5 services: postgres, redis, backend, celery_worker, frontend | One command starts the entire stack |
| `README.md` | This file | Architecture, file guide, API reference |

---

### `backend/` — Entry points

| File | What it is | Why it exists |
|---|---|---|
| `manage.py` | Django CLI | Runs migrations, dev server, shell |
| `Dockerfile` | Container build script | Installs deps, starts gunicorn in Docker |
| `requirements.txt` | Pinned Python dependencies | Reproducible installs |
| `.env` / `.env.example` | Runtime secrets | Keeps API keys out of source code |

---

### `backend/rag_assistant/` — Django project config

| File | What it is | Why it exists |
|---|---|---|
| `settings.py` | All Django config: DB, apps, CORS, Celery broker URL | Central config, reads secrets from `.env` |
| `urls.py` | Root URL router — mounts `/api/` prefix | Every URL must be registered here first |
| `wsgi.py` | WSGI entry point | Used by gunicorn in production |
| `celery.py` | Creates the Celery application object | Required for Celery to discover Django tasks |
| `__init__.py` | Imports Celery app at Django startup | Ensures Celery is initialised before any task is called |

---

### `backend/api/` — Application code

| File | What it is | Why it exists |
|---|---|---|
| `models.py` | Defines `Document` and `DocumentChunk` tables | ORM schema — Django generates SQL from these classes |
| `views.py` | HTTP handlers: ChatView, DocumentUploadView, DocumentStatusView, DocumentListView, DocumentDeleteView | Maps HTTP verbs to business logic |
| `serializers.py` | Input validation + JSON output formatting | Keeps validation out of views; DRF convention |
| `urls.py` | `/api/*` URL patterns | Connects URL paths to view classes |
| `tasks.py` | Celery task `ingest_document` | Runs the slow embedding loop outside the HTTP request |
| `admin.py` | Registers models in Django admin | Lets you browse DB records at `/admin/` |
| `apps.py` | App config class | Required by Django's app registry |

---

### `backend/api/migrations/` — Schema version history

| File | What it changes |
|---|---|
| `0001_initial.py` | Creates `Document` and `DocumentChunk` tables |
| `0002_advanced_rag.py` | Adds pgvector extension, HNSW index, `parent_text`, `page_number` |
| `0003_document_status.py` | Adds `status`, `chunks_total`, `chunks_done`, `error_message` to `Document` |

---

### `backend/api/services/` — RAG pipeline modules

Each service has a single responsibility. They never call each other in a circle.

| File | What it does | Who calls it |
|---|---|---|
| `document_processor.py` | Extracts text from PDF/TXT page-by-page (pdfplumber), tokenises sentences (NLTK), builds parent-child chunk pairs with 50% sliding window overlap | `tasks.py` |
| `embeddings.py` | Calls Gemini `gemini-embedding-001` with the correct task type and returns a 768-dim float list | `tasks.py`, `retrieval.py` |
| `query_processor.py` | Produces 4 query variants from the raw user question: rewritten query, 2 multi-query alternatives, 1 HyDE hypothetical passage | `retrieval.py` |
| `retrieval.py` | Runs BM25 + pgvector ANN cosine search for each query variant, fuses all ranked lists with RRF, returns top candidates | `views.py` |
| `reranking.py` | Sends all candidates to Gemini in one call, asks it to score each 1–10 for relevance, returns top-k | `views.py` |
| `llm.py` | Numbers passages, builds grounded-generation prompt, calls Gemini 2.5 Flash, extracts inline citation markers | `views.py` |
| `evaluation.py` | Measures faithfulness / answer relevancy / context relevancy using Gemini-as-judge (opt-in, adds ~3 API calls) | `views.py` |

---

### `frontend/` — Entry points

| File | What it is | Why it exists |
|---|---|---|
| `index.html` | HTML shell with `<div id="root">` | React mounts the entire app here |
| `main.jsx` | Creates React root, renders `<App />` | Vite starts bundling from here |
| `vite.config.js` | Build config + dev proxy (`/api → localhost:8000`) | Proxies API calls in dev so CORS is never an issue |
| `nginx.conf` | Production config: serves static files + proxies `/api/` to backend | Replaces the Vite proxy when running in Docker |
| `package.json` | JS dependencies + npm scripts | `npm run dev` / `npm run build` |
| `Dockerfile` | Builds static files with Vite, copies to nginx image | Lean production container |

---

### `frontend/src/` — React application

| File | What it does |
|---|---|
| `App.jsx` | Root component — owns tab state (`chat` / `documents`) and `docRefreshKey`; controls which panel is visible |
| `App.css` | Global layout styles: header, tab bar, shared colour tokens |
| `components/ChatInterface.jsx` | Chat panel: input box, message list, loading spinner, citation toggle; manages `messages`, `input`, `loading` state |
| `components/MessageBubble.jsx` | Renders one message: user bubble, assistant bubble with `[1][2]` citation cards, evaluation score chips |
| `components/DocumentUpload.jsx` | Drop zone, live progress bar (polls `/status/` every 2s), document list with delete buttons; manages `uploading`, `uploadProgress`, `documents` state |

---

## API Reference

### `POST /api/chat/`
```json
{ "question": "Who was Tsar Nicholas II?", "top_k": 5, "evaluate": false, "use_query_transform": true }
```
Response `200 OK`:
```json
{
  "answer": "Nicholas II was of the Romanov dynasty [1].",
  "citations": [{ "index": 1, "document_name": "history.pdf", "page_number": 4, "excerpt": "..." }],
  "sources_used": 5,
  "evaluation": { "faithfulness": 0.92, "answer_relevancy": 0.88, "context_relevancy": 0.85 }
}
```

### `POST /api/documents/upload/`
Multipart form-data, field `file`. PDF or TXT, max 100 MB. Returns `202 Accepted` immediately.
```json
{ "id": 42, "name": "doc.pdf", "status": "pending", "chunks_total": 0, "chunks_done": 0 }
```

### `GET /api/documents/<id>/status/`
```json
{ "id": 42, "status": "processing", "chunks_total": 2050, "chunks_done": 350, "error_message": "" }
```
`status` values: `pending` → `processing` → `done` | `failed`

### `GET /api/documents/`
Returns list with `status`, `chunk_count`, `chunks_done`, `chunks_total` per document.

### `DELETE /api/documents/<id>/`
Deletes document + all chunks (CASCADE). Returns `204 No Content`.

---

## Quick Start

### Option A — Native

```bash
# 1. PostgreSQL + pgvector
sudo apt install -y postgresql-16 postgresql-16-pgvector
sudo -u postgres psql -c "CREATE ROLE raguser WITH LOGIN PASSWORD 'StrongPass123!';"
sudo -u postgres psql -c "CREATE DATABASE ragdb OWNER raguser;"
sudo -u postgres psql -d ragdb -c "CREATE EXTENSION IF NOT EXISTS vector;"

# 2. Redis
sudo apt install -y redis-server

# 3. Backend (Terminal 1)
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # add GEMINI_API_KEY
python manage.py migrate
python manage.py runserver  # → http://localhost:8000

# 4. Celery worker (Terminal 2)
cd backend && source .venv/bin/activate
celery -A rag_assistant worker --loglevel=info

# 5. Frontend (Terminal 3)
cd frontend && npm install && npm run dev  # → http://localhost:5173
```

### Option B — Docker

```bash
cp backend/.env.example backend/.env
# set GEMINI_API_KEY in backend/.env
docker compose up --build
# App → http://localhost  |  API → http://localhost:8000
```

---

## Environment Variables (`backend/.env`)

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | Yes | Django secret key |
| `DEBUG` | Yes | `True` for dev, `False` in production |
| `ALLOWED_HOSTS` | Yes | Comma-separated hostnames |
| `CORS_ALLOWED_ORIGINS` | Yes | Comma-separated frontend origins |
| `GEMINI_API_KEY` | Yes | Google AI Studio API key |
| `POSTGRES_DB` | Yes | Database name (default: `ragdb`) |
| `POSTGRES_USER` | Yes | Database user (default: `raguser`) |
| `POSTGRES_PASSWORD` | Yes | Database password |
| `POSTGRES_HOST` | Yes | `localhost` (native) or `postgres` (Docker) |
| `POSTGRES_PORT` | No | Default: `5432` |
| `POSTGRES_SSLMODE` | No | `prefer` (local) or `require` (cloud DB) |
| `CELERY_BROKER_URL` | No | Default: `redis://localhost:6379/0` |
# RAG
