# Technical Documentation — Advanced RAG Document Assistant

## What is this project?

A **production-grade RAG (Retrieval-Augmented Generation)** application.  
You upload a PDF or TXT document. The system processes it through a multi-stage indexing pipeline and stores it in PostgreSQL with a vector index. When you ask a question, an 8-stage retrieval and generation pipeline finds the most relevant passages and returns a grounded answer with inline citations.

---

## Project Structure

```
AI asst/
├── docker-compose.yml
├── backend/
│   ├── api/
│   │   ├── models.py
│   │   ├── views.py
│   │   ├── serializers.py
│   │   ├── urls.py
│   │   ├── migrations/
│   │   │   ├── 0001_initial.py           # Base tables
│   │   │   └── 0002_advanced_rag.py      # pgvector ext + HNSW index
│   │   └── services/
│   │       ├── document_processor.py     # Semantic parent-child chunking
│   │       ├── embeddings.py             # Task-typed Gemini embeddings
│   │       ├── query_processor.py        # HyDE, multi-query, rewrite
│   │       ├── retrieval.py              # BM25 + pgvector ANN + RRF
│   │       ├── reranking.py              # LLM-as-judge reranking
│   │       ├── llm.py                    # Grounded generation + citations
│   │       └── evaluation.py             # Faithfulness / relevancy metrics
│   └── rag_assistant/
│       └── settings.py
└── frontend/
    └── src/components/
        ├── ChatInterface.jsx
        ├── MessageBubble.jsx             # Citation cards + eval badges
        └── DocumentUpload.jsx
```

---

## Flow 1 — Uploading a Document (Indexing Pipeline)

```
User picks a file
       │
       ▼
[React: DocumentUpload.jsx]
  POST /api/documents/upload/  (multipart/form-data)
       │
       ▼
[Django: DocumentUploadView]
  - Validates: PDF or TXT only, max 100 MB
       │
       ▼
[document_processor.py] — Semantic Parent-Child Chunking
  If PDF → pdfplumber extracts text page-by-page, preserving page numbers
  If TXT → decode UTF-8

  NLTK sentence tokenisation splits text into sentences.
  Sentences are grouped into:

    Child chunk  (CHILD_SENTENCES = 5 sentences)
      → small, precise retrieval unit
      → gets embedded and stored in the vector index
      
    Parent chunk (child + PARENT_PADDING = 3 sentences on each side)
      → wider context window
      → sent to LLM during generation for richer answers
      
  Step advances by CHILD_SENTENCES // 2 = 50% overlap so every
  sentence appears in at least two child chunks.
       │
       ▼
[embeddings.py — get_document_embedding()]
  For each child chunk:
    genai.embed_content(
        model="models/gemini-embedding-001",
        content=child_text,
        task_type="RETRIEVAL_DOCUMENT",   ← optimised for storage
        output_dimensionality=768,
    )
  Returns 768-dimensional vector.
       │
       ▼
[PostgreSQL: api_documentchunk]
  DocumentChunk.objects.bulk_create([
    DocumentChunk(
      document=doc,
      text=child_text,         # retrieval unit
      parent_text=parent_text, # generation context
      embedding=vector_768d,   # VectorField — stored as pgvector type
      chunk_index=i,
      page_number=page,
    )
  ])

  The HNSW index (created in migration 0002) automatically indexes
  each new embedding for O(log n) ANN queries.
```

---

## Flow 2 — Asking a Question (8-Stage Query Pipeline)

```
User types: "Who was Tsar Nicholas II?"
       │
       ▼
════════════════════════════════════════
STAGE 1 — Query Rewriting
[query_processor.py → rewrite_query()]
  Gemini rewrites the question:
  "Who was Tsar Nicholas II and what were his key characteristics?"
  
  Why: raw user input is often ambiguous or grammatically broken.
       A clean query produces better embeddings.
════════════════════════════════════════
       │
       ▼
════════════════════════════════════════
STAGE 2 — Multi-Query Generation
[query_processor.py → generate_multi_queries()]
  Generates 2 alternative phrasings, e.g.:
  "What role did Tsar Nicholas II play in Russian history?"
  "Describe the reign and downfall of Tsar Nicholas II"
  
  Why: the user's vocabulary may differ from the document's vocabulary.
       Multiple phrasings increase recall.
════════════════════════════════════════
       │
       ▼
════════════════════════════════════════
STAGE 3 — HyDE (Hypothetical Document Embeddings)
[query_processor.py → generate_hypothetical_document()]
  Gemini writes a fake answer passage:
  "Nicholas II was the last Russian Tsar of the Romanov dynasty.
   His weak leadership and reliance on Rasputin contributed..."
  
  This fake passage is EMBEDDED (not the question).
  Why: a passage about Nicholas II lives closer in vector space
       to real document chunks about Nicholas II than a question does.
════════════════════════════════════════
       │
       ▼  (now we have 4 embeddings: rewritten + 2 multi-query + HyDE)
════════════════════════════════════════
STAGE 4 — Hybrid Retrieval
[retrieval.py → bm25_search() + vector_search()]

  BM25 (keyword leg):
    rank_bm25.BM25Okapi on all child chunk texts.
    Excellent for: exact names ("Romanov"), codes, technical terms.
    Returns top-20 chunks ranked by BM25 score.

  pgvector ANN (semantic leg) × 4:
    For each of the 4 embeddings:
      DocumentChunk.objects
        .annotate(distance=CosineDistance("embedding", emb))
        .order_by("distance")[:20]
    Uses the HNSW index — O(log n) approximate nearest-neighbour.
    Excellent for: synonym matching, paraphrase, conceptual similarity.

  Result: 5 separate ranked lists.
════════════════════════════════════════
       │
       ▼
════════════════════════════════════════
STAGE 5 — Reciprocal Rank Fusion
[retrieval.py → reciprocal_rank_fusion()]

  Formula: score(chunk) = Σ over all lists of  1 / (60 + rank_in_list)

  A chunk ranked #1 in both BM25 and two vector lists scores very high.
  A chunk ranked #50 in one list scores almost nothing.

  Why RRF over score averaging:
    BM25 scores and cosine distances have incompatible scales.
    RRF uses only RANK — scale-invariant and robust.

  Returns top 15 candidates for the reranker.
════════════════════════════════════════
       │
       ▼
════════════════════════════════════════
STAGE 6 — LLM Reranking
[reranking.py → rerank_chunks()]

  All 15 candidates sent to Gemini in ONE prompt:
  "Rate each passage 1–10 for relevance to the question.
   Return JSON array: [8, 3, 7, ...]"

  Chunks sorted by score descending. Top 5 kept.

  Why: vector similarity is shallow — a chunk can be topically adjacent
       but not actually answer the question. Reranking considers the
       JOINT meaning of (query, chunk) together.
════════════════════════════════════════
       │
       ▼
════════════════════════════════════════
STAGE 7 — Grounded Generation with Citations
[llm.py → chat_with_context()]

  Uses parent_text of each chunk (wider context window).
  Prompt structure:
    [1] <parent_text of chunk 1>
    [2] <parent_text of chunk 2>
    ...
    "Answer using ONLY the numbered passages.
     Add citation number after each factual claim: [1]"

  Returns: { answer: "...text [1][2]...", citations: [...] }
════════════════════════════════════════
       │
       ▼
════════════════════════════════════════
STAGE 8 — Optional Evaluation
[evaluation.py → run_rag_evaluation()]  (only if evaluate=true)

  Three Gemini-as-judge calls:
  - Faithfulness:        fraction of answer claims in the context  (0–1)
  - Answer Relevancy:    does the answer address the question?      (0–1)
  - Context Relevancy:   are retrieved chunks relevant to query?    (0–1)
════════════════════════════════════════
       │
       ▼
[Django: ChatView returns]
{
  "answer": "Nicholas II was of the Romanov dynasty [1]...",
  "citations": [
    { "index": 1, "document_name": "history.pdf", "page_number": 4, "excerpt": "..." }
  ],
  "sources_used": 5,
  "evaluation": { "faithfulness": 0.92, "answer_relevancy": 0.88, ... }
}
       │
       ▼
[React: MessageBubble.jsx]
  - Renders answer with inline [1][2] markers
  - "N sources ▼" badge expands citation cards
  - Eval chips show colour-coded scores (green / yellow / red)
```

---

## Database Schema

### `api_document`
| Column | Type | Description |
|---|---|---|
| id | BigInt (PK) | Auto-generated |
| name | CharField(255) | Original filename |
| file_type | CharField(50) | `pdf` or `txt` |
| created_at | DateTimeField | Auto-set on upload |

### `api_documentchunk`
| Column | Type | Description |
|---|---|---|
| id | BigInt (PK) | Auto-generated |
| document_id | BigInt (FK) | → api_document, CASCADE delete |
| text | TextField | Child chunk — retrieval unit (~5 sentences) |
| parent_text | TextField | Wider context window — sent to LLM |
| embedding | vector(768) | pgvector column; HNSW-indexed |
| chunk_index | IntegerField | 0-based position in document |
| page_number | IntegerField (nullable) | Source PDF page |

### Indexes on `api_documentchunk`
| Index | Type | Purpose |
|---|---|---|
| `api_documentchunk_pkey` | B-tree | Primary key lookup |
| `api_documentchunk_document_id_*` | B-tree | FK join / cascade delete |
| `documentchunk_embedding_hnsw` | HNSW (vector_cosine_ops) | ANN cosine search |

---

## Key Concepts

### Why task-type embeddings?
Gemini's embedding model is trained with separate task types. Using `RETRIEVAL_DOCUMENT` when indexing and `RETRIEVAL_QUERY` when querying shifts the vector space to be optimally aligned for retrieval — measurably improving recall versus using a single generic task type.

### Why parent-child chunks?
Small child chunks (5 sentences) produce precise, focused embeddings — good for retrieval. But sending only 5 sentences to the LLM may truncate the full context of an answer. The parent chunk (child + 3 sentences each side) gives the LLM enough surrounding text to answer coherently without resorting to hallucination.

### Why BM25 + vector hybrid?
- BM25 wins on: exact names, product codes, unusual terms, numbers.
- Dense vector wins on: paraphrase, synonyms, conceptual questions.
- Neither alone is optimal. Hybrid reliably outperforms either alone.

### Why RRF over score averaging?
BM25 scores and cosine distances live on incompatible scales. Normalising them requires assumptions. RRF only uses rank — which is universal. The constant k=60 dampens the effect of very high ranks, giving moderate-quality results more influence than a pure winner-takes-all scheme.

### Why LLM reranking after vector search?
Vector similarity measures how close two embedding vectors are — it is a semantic proxy, not a direct relevance measure. A chunk about "Nicholas II's railway policy" is semantically close to "Nicholas II" but doesn't answer "Who was he?". A reranker reads the actual text of both the query and the chunk together and scores true relevance.

---

## API Endpoints

| Method | URL | Body | Response |
|---|---|---|---|
| `POST` | `/api/chat/` | `{question, top_k, evaluate, use_query_transform}` | `{answer, citations, sources_used, evaluation?}` |
| `GET` | `/api/documents/` | — | `[{id, name, file_type, created_at, chunk_count}]` |
| `POST` | `/api/documents/upload/` | `file` (multipart) | `{id, name, file_type, created_at, chunk_count}` |
| `DELETE` | `/api/documents/<id>/` | — | `204 No Content` |

---

## External Services

| Service | Model | Purpose | Free Tier |
|---|---|---|---|
| Google Gemini | `gemini-embedding-001` | Text → 768-dim vector | 100 req/min |
| Google Gemini | `gemini-2.5-flash` | Generation, reranking, eval | 15 req/min, 1500/day |

---

## Docker Setup

```
docker-compose.yml
       │
       ├── postgres (pgvector/pgvector:pg16, port 5432)
       │     - pgvector extension pre-installed
       │     - Health-check before backend starts
       │     - Volume: postgres_data (persistent)
       │
       ├── backend (port 8000)
       │     - Django + Gunicorn
       │     - Waits for postgres health-check
       │     - Volume: ./backend/uploads
       │
       └── frontend (port 80)
             - Vite build → Nginx static serve
             - Nginx proxies /api/* → backend:8000
```


---

## Project Structure

```
AI asst/
├── docker-compose.yml          # Runs everything together
├── backend/                    # Python/Django server (the brain)
│   ├── api/
│   │   ├── models.py           # Database table definitions
│   │   ├── views.py            # API endpoint handlers
│   │   ├── serializers.py      # Data formatting
│   │   ├── urls.py             # URL routes
│   │   └── services/
│   │       ├── document_processor.py   # Reads PDF/TXT files
│   │       ├── embeddings.py           # Converts text to numbers (vectors)
│   │       ├── retrieval.py            # Finds relevant text chunks
│   │       └── llm.py                  # Talks to Gemini AI
│   └── rag_assistant/
│       └── settings.py         # Django configuration
└── frontend/                   # React user interface
    └── src/
        └── components/
            ├── ChatInterface.jsx       # Chat window
            ├── DocumentUpload.jsx      # Upload panel
            └── MessageBubble.jsx       # Individual message display
```

---

## How the Flow Works

### Flow 1 — Uploading a Document

```
User picks a file
       │
       ▼
[React: DocumentUpload.jsx]
  - Sends file via POST /api/documents/upload/
       │
       ▼
[Django: DocumentUploadView]
  - Validates file (PDF or TXT, max 100MB)
  - Reads the raw bytes of the file
       │
       ▼
[document_processor.py]
  - If PDF  → pdfplumber extracts all text from every page
  - If TXT  → decodes bytes to string
  - Splits text into chunks of 500 characters with 50-char overlap
    Example: "The quick brown fox..." becomes many small pieces
       │
       ▼
[embeddings.py] — called for EACH chunk
  - Sends the chunk text to Google Gemini API
  - Model: gemini-embedding-001
  - Returns a list of ~3000 numbers (a "vector") that represents the meaning
       │
       ▼
[SQLite Database]
  - Saves a Document record (name, file type, date)
  - Saves a DocumentChunk record for each chunk:
      • the original text
      • its embedding (list of numbers stored as JSON)
      • its index (position in the document)
```

**Why chunks?** AI models have limits on how much text they can process at once. Breaking documents into chunks lets us find only the relevant parts instead of sending the entire document every time.

**Why embeddings?** Embeddings turn text into numbers in a way that captures meaning. Similar sentences end up with similar numbers — so we can do math to find related content.

---

### Flow 2 — Asking a Question (Chat)

```
User types a question and presses Send
       │
       ▼
[React: ChatInterface.jsx]
  - Shows the user message immediately
  - Sends POST /api/chat/ with { "question": "..." }
       │
       ▼
[Django: ChatView]
  - Validates the request
  - Calls retrieve_top_k(question, top_k=5)
       │
       ▼
[retrieval.py]
  - Embeds the question using the same Gemini embedding model
    (turns the question into the same type of number vector)
  - Loads ALL DocumentChunk embeddings from the database
  - Computes cosine similarity between the question vector and every chunk vector
  
    Cosine similarity = how "close" two vectors are in direction
    Score of 1.0 = identical meaning
    Score of 0.0 = completely unrelated
    
  - Sorts all chunks by similarity score (highest first)
  - Returns the top 5 most relevant chunk texts
       │
       ▼
[llm.py]
  - Assembles a prompt:
      "Here is context from the document:
       [chunk 1 text]
       ---
       [chunk 2 text]
       ...
       
       Question: [user's question]"
  - Sends this to Gemini 2.5 Flash
  - Returns the generated answer
       │
       ▼
[Django: ChatView]
  - Returns { answer: "...", sources_used: 5 }
       │
       ▼
[React: ChatInterface.jsx]
  - Displays the answer as an assistant message bubble
```

---

## Key Concepts Explained Simply

### What is RAG?
RAG = **Retrieve** relevant context → **Augment** the prompt with it → **Generate** an answer.

Without RAG, the AI only knows what it was trained on. With RAG, the AI can answer questions about *your specific documents* by being shown the relevant parts at question time.

### What is an Embedding?
An embedding is a list of numbers (a vector) that represents the *meaning* of a piece of text. For example:
- "The dog ran fast" and "The puppy sprinted quickly" → very similar vectors
- "The dog ran fast" and "Stock markets fell today" → very different vectors

This lets us do mathematical search for meaning, not just keyword matching.

### What is Cosine Similarity?
It measures the angle between two vectors. A small angle (score near 1.0) means the texts have similar meaning. Used in `retrieval.py` to rank chunks by relevance to the question.

---

## Database Tables

### `api_document`
| Column | Type | Description |
|---|---|---|
| id | Integer | Auto-generated primary key |
| name | Text | Original filename |
| file_type | Text | "pdf" or "txt" |
| created_at | DateTime | Upload timestamp |

### `api_documentchunk`
| Column | Type | Description |
|---|---|---|
| id | Integer | Auto-generated primary key |
| document_id | Integer | Links to api_document |
| text | Text | The actual chunk text (500 chars) |
| embedding | JSON | List of ~3000 floats (the vector) |
| chunk_index | Integer | Position of chunk in the document |

---

## API Endpoints

| Method | URL | What it does |
|---|---|---|
| `GET` | `/api/documents/` | List all uploaded documents |
| `POST` | `/api/documents/upload/` | Upload a new document |
| `DELETE` | `/api/documents/<id>/` | Delete a document and all its chunks |
| `POST` | `/api/chat/` | Ask a question, get an answer |

---

## External Services Used

| Service | Model | Purpose | Free Tier |
|---|---|---|---|
| Google Gemini | `gemini-embedding-001` | Convert text to vectors | 100 req/min |
| Google Gemini | `gemini-2.5-flash` | Generate answers | 15 req/min, 1500/day |

---

## Docker Setup

```
docker-compose.yml
       │
       ├── backend container (port 8000)
       │     - Runs Django + Gunicorn (Python web server)
       │     - On startup: runs database migrations, then starts server
       │     - Volume: ./backend/uploads → stores uploaded files
       │     - Volume: sqlite_data:/app/data → persists the database
       │
       └── frontend container (port 80)
             - Builds React app with Vite (at Docker build time)
             - Serves static files via Nginx
             - Nginx also proxies /api/* requests → backend:8000
             - This is why the frontend can call /api/ without CORS issues
```

**Why Nginx as a proxy?**
The browser talks only to Nginx on port 80. Nginx serves the React files and forwards any `/api/` request to Django on port 8000. This avoids CORS (cross-origin) problems and is the standard production pattern.

---

## What Happens When You Run `docker compose up --build`

1. Docker builds the **backend** image: installs Python packages, copies code
2. Docker builds the **frontend** image: runs `npm install` + `npm run build`, then packages the output into Nginx
3. Docker starts both containers
4. Backend runs `python manage.py migrate` → creates all database tables
5. Backend starts Gunicorn with 2 worker processes
6. Nginx starts and is ready to serve requests
7. App is live at http://localhost
