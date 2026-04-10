# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the server (with dependency/env checks and auto-reload)
python run.py
```

The server runs at `http://localhost:8000`. API docs are auto-generated at `/docs`.

## Environment

Required variables in `.env`:
```
DEEPSEEK_API_KEY=your_key_here
ADMIN_API_KEY=secret_for_admin_upload
```

Optional:
```
LOG_LEVEL=INFO   # DEBUG | INFO | WARNING | ERROR
```

## Architecture

This is a RAG (Retrieval-Augmented Generation) API for insurance document analysis built on **Clean Architecture**. The flow is:

1. **PDF Upload** → `PdfDocumentParser` extracts text page-by-page with `pypdf`
2. **Chunking** → `InsuranceSemanticChunker` splits at clause/paragraph boundaries (1200-char target, 200-char overlap), with cross-page overlap handled in `IngestDocument`
3. **Vectorization** → `FAISSVectorRepository` encodes chunks with `sentence-transformers` (`all-MiniLM-L6-v2`, 384-dim) and persists to FAISS + SQLite
4. **Query** → `AskInsuranceQuestion` use case: FAISS top-K → `KeywordOverlapReranker` (70% semantic + 30% term overlap) → `DeepSeekGateway`
5. **Generation** → DeepSeek `deepseek-chat` returns a structured 4-section audit response (timeout 30s, 3 retries)

### Layer responsibilities

| Layer | Path | Responsibility |
|---|---|---|
| **Domain** | `app/domain/` | Pure entities and abstract interfaces — no I/O, no frameworks |
| **Use Cases** | `app/use_cases/` | Business logic orchestration via injected interfaces |
| **Infrastructure** | `app/infrastructure/` | Concrete implementations (FAISS, SQLite, pypdf, DeepSeek) |
| **API** | `app/api/` | FastAPI routes — HTTP concerns only, delegates to use cases |

### Folder structure

```
app/
├── domain/
│   ├── entities/
│   │   └── document.py        # InsuranceMetadata (Value Object), Chunk, SearchResult, ParsedPage
│   └── interfaces/
│       ├── text_chunker.py    # TextChunker ABC
│       ├── reranker.py        # Reranker ABC
│       ├── vector_repository.py  # VectorRepository ABC: add/search/delete/has_document/count
│       ├── document_parser.py # DocumentParser ABC
│       └── llm_gateway.py     # LLMGateway ABC
├── use_cases/
│   ├── ingest_document.py     # IngestDocument: parse → chunk → dedup → add
│   └── answer_question.py     # AskInsuranceQuestion: search → rerank → generate
├── infrastructure/
│   ├── chunkers/
│   │   └── semantic_chunker.py   # InsuranceSemanticChunker
│   ├── rerankers/
│   │   └── keyword_reranker.py   # KeywordOverlapReranker
│   ├── parsers/
│   │   └── pdf_parser.py         # PdfDocumentParser (pypdf)
│   ├── repositories/
│   │   ├── faiss_repository.py   # FAISSVectorRepository (implements VectorRepository)
│   │   └── sqlite_metadata.py    # SQLiteMetadataStore (substitutes legacy pickle)
│   └── gateways/
│       └── deepseek_gateway.py   # DeepSeekGateway (implements LLMGateway)
├── api/
│   └── routes/
│       ├── ask.py          # POST /ask  →  AskInsuranceQuestion
│       ├── upload.py       # POST /upload, POST /admin/upload  →  IngestDocument
│       └── health.py       # GET /, /health, /status, /stats, /metrics
├── services/               # LEGACY — kept for reference, no longer wired
│   ├── llm_service.py
│   ├── vector_service.py
│   └── document_service.py
├── models/
│   ├── requests.py         # AskRequest (Pydantic v2)
│   └── responses.py        # AskResponse, UploadResponse, ContextItem
├── core/
│   ├── config.py           # Settings (pydantic-settings) + constants
│   ├── dependencies.py     # Singletons via lru_cache; exposes get_ask_use_case / get_ingest_use_case
│   ├── metrics.py          # MetricsStore + module-level singleton
│   └── logging.py          # _JsonFormatter + setup_logging()
└── main.py                 # FastAPI app, CORS, static mount, routers, warm_up startup
static/
├── index.html
├── app.css
└── app.js
```

### Dependency injection

Use cases are assembled in [app/core/dependencies.py](app/core/dependencies.py) and injected via FastAPI `Depends`. Infrastructure singletons are created with `lru_cache`:

```python
# dependencies.py
def get_ask_use_case() -> AskInsuranceQuestion:
    return AskInsuranceQuestion(_vector_repo(), _reranker(), _llm_gateway())

# route
@router.post("/ask")
async def ask_question(data: AskRequest, use_case: AskInsuranceQuestion = Depends(get_ask_use_case)):
    answer, context = use_case.execute(question=data.question, ...)
```

### Key files

- [app/domain/entities/document.py](app/domain/entities/document.py) — `InsuranceMetadata` Value Object (normalizes `tipo`/`seguradora`), `Chunk`, `SearchResult`, `ParsedPage`.
- [app/domain/interfaces/vector_repository.py](app/domain/interfaces/vector_repository.py) — `VectorRepository` ABC: `add(chunks)`, `search(query, n, filter)`, `delete(doc_id)`, `has_document`, `count`.
- [app/use_cases/ingest_document.py](app/use_cases/ingest_document.py) — `IngestDocument.execute(file_path, metadata, source_name)`: orchestrates parse → chunk → dedup → add. Owns cross-page overlap logic and `doc_id` generation (MD5 hash).
- [app/use_cases/answer_question.py](app/use_cases/answer_question.py) — `AskInsuranceQuestion.execute(question, top_k, filter_dict, ...)`: search → rerank → generate. Returns `(answer, reranked_results)`.
- [app/infrastructure/repositories/faiss_repository.py](app/infrastructure/repositories/faiss_repository.py) — `FAISSVectorRepository`: pure vector store. Composes `SQLiteMetadataStore`; auto-migrates from legacy `metadata.pkl` on first load.
- [app/infrastructure/repositories/sqlite_metadata.py](app/infrastructure/repositories/sqlite_metadata.py) — `SQLiteMetadataStore`: persists chunk metadata + texts in `faiss_db/metadata.db`. Manages `faiss_pos` renumbering after deletions.
- [app/infrastructure/chunkers/semantic_chunker.py](app/infrastructure/chunkers/semantic_chunker.py) — `InsuranceSemanticChunker`: clause/paragraph boundary detection via regex, falls back to fixed-size split.
- [app/infrastructure/rerankers/keyword_reranker.py](app/infrastructure/rerankers/keyword_reranker.py) — `KeywordOverlapReranker`: 70% FAISS score + 30% PT term overlap, filters stopwords.
- [app/infrastructure/gateways/deepseek_gateway.py](app/infrastructure/gateways/deepseek_gateway.py) — `DeepSeekGateway`: wraps `openai` SDK, holds the auditor system prompt, formats `SearchResult` objects into the LLM context string.
- [app/core/dependencies.py](app/core/dependencies.py) — single wiring point; `get_ask_use_case`, `get_ingest_use_case`, plus `get_vector_service`/`get_llm_service` for health routes.
- [app/main.py](app/main.py) — FastAPI app, CORS, `/static` mount, routers, `warm_up` startup event.

### API: /ask request body

```json
{ "question": "...", "top_k": 10, "filter": {"seguradora": "Bradesco"} }
```
`top_k` is clamped 1–20. `filter` is optional; omit or pass `null` for all insurers.

### /admin/upload authentication

Requires `X-Admin-Key: <ADMIN_API_KEY>` header. Returns 401 otherwise. Also validates `seguradora` against `ALLOWED_SEGURADORAS` (delivery-layer concern — domain allows "Desconhecida").

### FAISS + SQLite persistence

- `faiss_db/faiss_index.bin` — FAISS binary index
- `faiss_db/metadata.db` — SQLite: chunk texts, metadata and `faiss_pos` mapping
- Legacy `faiss_db/metadata.pkl` is auto-migrated to SQLite on first startup if present
- Re-uploading the same PDF (same MD5 hash) removes old chunks before reindexing

### Observability

- `GET /metrics` — `{"queries_24h": N, "avg_retrieval_ms": X, "avg_llm_ms": Y, "avg_total_ms": Z}`
- Structured JSON logs to stdout; each query emits `{"event": "query", "total_ms": ..., "chunks": ..., ...}`
- `LOG_LEVEL` env var controls verbosity (default `INFO`)

### Legacy services (app/services/)

`vector_service.py`, `llm_service.py` and `document_service.py` are **no longer wired** — kept for reference only. Safe to delete once the new architecture is validated in production.
