# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the server (with dependency/env checks and auto-reload)
python run.py

# Bulk-ingest PDFs interactively (uses the same IngestDocument use case as the API)
python ingest.py [--pdf-dir ./pdfs]
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

RAG (Retrieval-Augmented Generation) API for insurance document analysis built on **Clean Architecture**. The full pipeline is:

1. **PDF Upload** → `PdfDocumentParser` extracts text page-by-page (`pypdf`)
2. **Chunking** → `InsuranceSemanticChunker` splits at clause/paragraph/article boundaries (1200-char target, 200-char overlap); cross-page overlap is handled inside `IngestDocument`
3. **Deduplication** → `IngestDocument` computes SHA-256 of the file; if hash exists in the `DocumentCatalog`, skips re-embedding or only updates metadata in-place
4. **Vectorization** → `FAISSVectorRepository` encodes chunks with `sentence-transformers` (`all-MiniLM-L6-v2`, 384-dim) and persists to FAISS + SQLite
5. **Query** → `AskInsuranceQuestion`: FAISS top-K → `KeywordOverlapReranker` (70% semantic + 30% PT term overlap) → `DeepSeekGateway`
6. **Generation** → DeepSeek `deepseek-chat`, structured 4-section audit response (timeout 30s, 3 retries with exponential backoff)

### Layer responsibilities

| Layer | Path | Responsibility |
|---|---|---|
| **Domain** | `app/domain/` | Pure entities, value objects, enums and abstract interfaces — no I/O |
| **Use Cases** | `app/use_cases/` | Business logic orchestration via injected interfaces |
| **Infrastructure** | `app/infrastructure/` | Concrete implementations (FAISS, SQLite, pypdf, DeepSeek) |
| **API** | `app/api/` | FastAPI routes — HTTP concerns only, delegates to use cases |

### Folder structure

```
app/
├── domain/
│   ├── entities/
│   │   ├── document.py      # InsuranceMetadata (VO), Chunk, SearchResult, ParsedPage, DocumentRecord
│   │   └── insurance.py     # Seguradora (str Enum), DocumentType (str Enum), Ramo (str Enum)
│   └── interfaces/
│       ├── text_chunker.py       # TextChunker ABC
│       ├── reranker.py           # Reranker ABC
│       ├── vector_repository.py  # VectorRepository ABC: add/search/delete/update_metadata/count
│       ├── document_parser.py    # DocumentParser ABC
│       ├── document_catalog.py   # DocumentCatalog ABC: register/find_by_hash/update_metadata/list_all
│       └── llm_gateway.py        # LLMGateway ABC
├── use_cases/
│   ├── ingest_document.py   # IngestDocument: parse → chunk → SHA-256 dedup → add → catalog
│   ├── answer_question.py   # AskInsuranceQuestion: search → rerank → generate
│   └── get_inventory.py     # GetInventory: list catalog grouped by seguradora
├── infrastructure/
│   ├── chunkers/
│   │   └── semantic_chunker.py    # InsuranceSemanticChunker (Rust/PyO3 target flagged)
│   ├── rerankers/
│   │   └── keyword_reranker.py    # KeywordOverlapReranker
│   ├── parsers/
│   │   └── pdf_parser.py          # PdfDocumentParser (pypdf)
│   ├── repositories/
│   │   ├── faiss_repository.py    # FAISSVectorRepository (VectorRepository impl)
│   │   ├── sqlite_metadata.py     # SQLiteMetadataStore — chunks table, faiss_pos sync
│   │   └── sqlite_catalog.py      # SQLiteDocumentCatalog (DocumentCatalog impl) — documents table
│   └── gateways/
│       └── deepseek_gateway.py    # DeepSeekGateway (LLMGateway impl)
├── api/
│   └── routes/
│       ├── ask.py           # POST /ask  →  AskInsuranceQuestion
│       ├── upload.py        # POST /upload, POST /admin/upload  →  IngestDocument
│       ├── inventory.py     # GET /api/inventory  →  GetInventory
│       └── health.py        # GET /, /health, /status, /stats, /metrics
├── models/
│   ├── requests.py          # AskRequest (Pydantic v2)
│   └── responses.py         # AskResponse, UploadResponse, ContextItem
├── core/
│   ├── config.py            # Settings (pydantic-settings); ALLOWED_SEGURADORAS and
│   │                        #   ALLOWED_DOCUMENT_TYPES derived from domain enums
│   ├── dependencies.py      # Single wiring point — lru_cache singletons + use case factories
│   ├── metrics.py           # MetricsStore (in-memory 24h latencies) + singleton
│   └── logging.py           # _JsonFormatter + setup_logging()
└── main.py                  # FastAPI app, CORS, /static mount, all routers, warm_up startup
static/
├── index.html
├── app.css
└── app.js
faiss_db/                    # Committed to repo for Render free-tier deploy (no persistent disk)
├── faiss_index.bin          # FAISS binary index
└── metadata.db              # SQLite: chunks table (faiss_pos) + documents table (catalog)
```

### Dependency injection

All use cases are assembled in [app/core/dependencies.py](app/core/dependencies.py) via `lru_cache` singletons and injected into routes with FastAPI `Depends`:

```python
# dependencies.py
def get_ingest_use_case() -> IngestDocument:
    return IngestDocument(_parser(), _chunker(), _vector_repo(), _document_catalog())

def get_ask_use_case() -> AskInsuranceQuestion:
    return AskInsuranceQuestion(_vector_repo(), _reranker(), _llm_gateway())

def get_inventory_use_case() -> GetInventory:
    return GetInventory(_document_catalog())
```

### Key files

- [app/domain/entities/insurance.py](app/domain/entities/insurance.py) — `Seguradora`, `DocumentType`, and `Ramo` as `str, Enum`. `Seguradora.allowed_for_admin()` returns the allowlist used by `/admin/upload`. `config.py` derives `ALLOWED_SEGURADORAS` / `ALLOWED_DOCUMENT_TYPES` from these — no magic strings anywhere.
- [app/domain/entities/document.py](app/domain/entities/document.py) — `InsuranceMetadata` Value Object (fields: `seguradora`, `ano`, `tipo`, `ramo`), `Chunk`, `SearchResult`, `ParsedPage`, `DocumentRecord` (catalog entry with `file_hash`, `chunk_count`, `created_at`, `ramo`).
- [app/domain/interfaces/vector_repository.py](app/domain/interfaces/vector_repository.py) — `VectorRepository` ABC: `add`, `search`, `delete`, `update_metadata` (in-place without re-embedding), `has_document`, `count`.
- [app/domain/interfaces/document_catalog.py](app/domain/interfaces/document_catalog.py) — `DocumentCatalog` ABC: `register`, `find_by_hash`, `update_metadata(doc_id, seguradora, ano, tipo, ramo)`, `remove`, `list_all`, `total_chunks`.
- [app/use_cases/ingest_document.py](app/use_cases/ingest_document.py) — `IngestDocument.execute(file_path, metadata, source_name)`. SHA-256 dedup: skip if identical hash+metadata (including `ramo`) / update metadata in-place if content unchanged / full re-index if new. Owns cross-page overlap logic.
- [app/use_cases/answer_question.py](app/use_cases/answer_question.py) — `AskInsuranceQuestion.execute(question, top_k, filter_dict, ...)` → `(answer, reranked_results)`.
- [app/use_cases/get_inventory.py](app/use_cases/get_inventory.py) — `GetInventory.execute()` → `{total_documents, total_chunks, by_seguradora, documents}`.
- [app/infrastructure/repositories/faiss_repository.py](app/infrastructure/repositories/faiss_repository.py) — `FAISSVectorRepository`: pure vector ops. Composes `SQLiteMetadataStore`. Auto-migrates legacy `metadata.pkl` to SQLite on first load.
- [app/infrastructure/repositories/sqlite_metadata.py](app/infrastructure/repositories/sqlite_metadata.py) — `SQLiteMetadataStore`: `chunks` table. Manages `faiss_pos` renumbering after deletions. `update_document_metadata` patches seguradora/ano/tipo/ramo without touching embeddings.
- [app/infrastructure/repositories/sqlite_catalog.py](app/infrastructure/repositories/sqlite_catalog.py) — `SQLiteDocumentCatalog`: `documents` table in the same `metadata.db`. Stores one row per PDF with `file_hash` (SHA-256 UNIQUE), `chunk_count`, `created_at`, `ramo`.
- [app/infrastructure/chunkers/semantic_chunker.py](app/infrastructure/chunkers/semantic_chunker.py) — `InsuranceSemanticChunker`. `_fixed_chunk` is marked as **Rust/PyO3 optimization target**.
- [app/infrastructure/gateways/deepseek_gateway.py](app/infrastructure/gateways/deepseek_gateway.py) — `DeepSeekGateway`: wraps `openai` SDK, owns the auditor system prompt, formats `List[SearchResult]` into the LLM context string.
- [app/core/dependencies.py](app/core/dependencies.py) — single wiring point. Exposes `get_ask_use_case`, `get_ingest_use_case`, `get_inventory_use_case`, `get_vector_service`, `get_llm_service`, `get_document_catalog`.
- [ingest.py](ingest.py) — CLI bulk-ingestion de alta produtividade. Fluxo em 4 fases: coleta de metadados com auto-detect + session memory → resumo do lote com prévia de renomeação → renomeação física → indexação. Usa `get_ingest_use_case()` — caminho idêntico à API.

### API endpoints

| Method | Path | Handler |
|---|---|---|
| `GET` | `/` | Serves `static/index.html` |
| `GET` | `/health` | Vector store stats |
| `GET` | `/status` | `{total_chunks, ready}` |
| `GET` | `/stats` | Vector store + inventory summary + LLM connectivity |
| `GET` | `/metrics` | 24h query latencies |
| `POST` | `/upload` | Open upload (seguradora optional) |
| `POST` | `/admin/upload` | Validated upload (requires `X-Admin-Key`, seguradora from allowlist) |
| `POST` | `/ask` | RAG query |
| `GET` | `/api/inventory` | Document catalog grouped by seguradora |

### Ramo enum

`Ramo` (`app/domain/entities/insurance.py`) diferencia manuais de ramos distintos para evitar confusão entre, por exemplo, Agrícola e Construção Civil da mesma seguradora:

| Valor | Descrição |
|---|---|
| `Agricola` | Seguro agrícola / rural |
| `Automovel` | Seguro de automóvel |
| `PME` | Seguro para pequenas e médias empresas |
| `Construcao Civil` | Riscos de engenharia / construção civil |
| `Residencial` | Seguro residencial |
| `Desconhecido` | Ramo não identificado (padrão) |

`ramo` está presente em todas as camadas: `InsuranceMetadata`, `Chunk`, `SearchResult`, `DocumentRecord`, tabelas `chunks` e `documents` no SQLite, rotas `/upload` e `/admin/upload` (o endpoint admin valida `ramo` contra `_ALLOWED_RAMOS`).

### /ask request body

```json
{ "question": "...", "top_k": 10, "filter": {"seguradora": "Bradesco"} }
```
`top_k` clamped 1–20. `filter` optional.

### Deduplication flow (IngestDocument)

```
SHA-256(file) → catalog.find_by_hash()
  ├─ not found          → full ingest (parse → chunk → embed → add → catalog.register)
  ├─ found, same meta   → skip (return existing chunk_count)
  └─ found, diff meta   → catalog.update_metadata + vector_repo.update_metadata (no re-embed)
```

### FAISS + SQLite persistence

Both files live in `faiss_db/` and are **committed to the repo** so Render free-tier (no persistent disk) can serve a pre-built index after each deploy.

- `faiss_db/faiss_index.bin` — FAISS binary index (vectors only)
- `faiss_db/metadata.db` — SQLite with two tables:
  - `chunks(faiss_pos, doc_id, text, source, page, seguradora, ano, tipo, ramo, chunk_index)` — managed by `SQLiteMetadataStore`
  - `documents(doc_id PK, source_name, file_hash UNIQUE, seguradora, ano, tipo, ramo, chunk_count, created_at)` — managed by `SQLiteDocumentCatalog`
- Legacy `faiss_db/metadata.pkl` is auto-migrated to `chunks` table on first startup if `metadata.db` is empty

### Docker / Render deploy

```dockerfile
# Model pre-downloaded into the image (~90 MB) — eliminates ~60s cold start
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
# Single worker to stay within Render free-tier 512 MB RAM
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1
```

`HF_HOME=/app/model_cache` keeps the Hugging Face cache at a predictable path inside the container.

### ingest.py — CLI de alta produtividade

Fluxo em 4 fases (nenhum arquivo é tocado até a confirmação do usuário):

```
Fase 1 — Coleta de metadados (por arquivo)
  ├─ Auto-detect: busca Seguradora / Ramo / Ano no nome do arquivo por substring
  │   normalizada (case-insensitive, sem underscores/hífens).
  │   Enums ordenados do mais longo ao mais curto para evitar falsos positivos.
  ├─ Session memory: se nada foi detectado, oferece o valor do arquivo anterior
  │   como padrão — útil para lotes da mesma seguradora.
  └─ Confirmação rápida: Enter aceita a sugestão/padrão; qualquer outro valor
      é resolvido como índice numérico ou nome (case-insensitive).

Fase 2 — Resumo do lote
  ├─ Tabela com Arquivo / Seguradora / Ramo / Ano / Tipo.
  ├─ Seção "Renomeação prevista": lista orig → novo para todos os arquivos
  │   que mudarão de nome.
  └─ Pergunta S/n — 'n' cancela sem nenhum efeito colateral.

Fase 3 — Renomeação física (apenas após confirmação)
  ├─ Novo nome: {Seguradora}_{Ramo}_{Tipo}_{Ano}_{suffix5}.pdf
  │   suffix5 = primeiros 5 hex do SHA-1 do stem original (determinístico).
  │   Espaços → underscores; caracteres especiais removidos (re.ASCII).
  ├─ Se src == dst → skip silencioso (re-run seguro).
  ├─ Se dst já existe e é diferente → aviso + mantém nome original.
  └─ OSError (permissão, arquivo aberto) → aviso + mantém nome original.

Fase 4 — Indexação (get_ingest_use_case importado apenas aqui)
  ├─ FAISS e o modelo de embeddings só são carregados se o usuário confirmou.
  ├─ source_name passado ao IngestDocument já reflete o nome renomeado.
  └─ Erros por arquivo são capturados; o lote continua e o relatório final
      lista as falhas.
```

Exemplo de nome gerado: `Bradesco_Agricola_Cobertura_2025_559ae.pdf`

### Observability

- `GET /metrics` — `{"queries_24h": N, "avg_retrieval_ms": X, "avg_llm_ms": Y, "avg_total_ms": Z}`
- `GET /stats` — includes `"inventory": {"total_documents": N, "total_chunks": N}`
- Structured JSON logs to stdout; each query emits `{"event": "query", "total_ms": ..., "chunks": ..., ...}`
- `LOG_LEVEL` env var controls verbosity (default `INFO`)