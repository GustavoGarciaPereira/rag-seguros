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

# Wipe index and re-index all PDFs from scratch (non-interactive, uses filename auto-detect)
python reindex.py [--pdf-dir ./pdfs] [--yes]

# Retrieval quality regression test (no pytest, exit 0 = pass, exit 1 = fail)
python test_regression.py
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
2. **Chunking** → `InsuranceSemanticChunker` splits at clause/paragraph/article boundaries (1200-char target, 200-char overlap); cross-page overlap is handled inside `IngestDocument`. Each chunk is prefixed with its parent section title (`[SEÇÃO: <título>]\n`) to improve semantic score of tables and lists relative to dense paragraphs.
3. **Deduplication** → `IngestDocument` computes SHA-256 of the file; if hash exists in the `DocumentCatalog`, skips re-embedding or only updates metadata in-place
4. **Vectorization** → `FAISSVectorRepository` encodes chunks with `sentence-transformers` (`all-MiniLM-L6-v2`, 384-dim) and persists to FAISS + SQLite
5. **Query** → `AskInsuranceQuestion`: FAISS fetch_k (= top_k × 4, default 60) → `KeywordOverlapReranker` (70% semantic + 30% PT term overlap) → slice top_k → `DeepSeekGateway`
6. **Generation** → DeepSeek `deepseek-chat` via **SSE streaming** (`stream=True`); 4-section audit response with Chain-of-Thought (Análise Prévia Silenciosa), cross-reference resolution and formula transcription; max_tokens 4000, timeout 30s, 3 retries with exponential backoff (non-streaming path only)

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
│       └── llm_gateway.py        # LLMGateway ABC: generate (sync) + generate_stream (Iterator[str])
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
- [app/use_cases/answer_question.py](app/use_cases/answer_question.py) — `AskInsuranceQuestion`. Two public methods: `execute(...)` → `(answer, reranked_results)` (non-streaming, used by health/test paths); `execute_stream(...)` → `(reranked_results, Iterator[str])` — does FAISS search + reranking eagerly, returns a lazy text generator for SSE. Both implement **oversampling**: FAISS is queried with `fetch_k = top_k * 4`, the reranker scores all candidates, and a final `[:top_k]` slice keeps only the best results for the LLM. Both emit `DEBUG` logs for recall debugging.
- [app/use_cases/get_inventory.py](app/use_cases/get_inventory.py) — `GetInventory.execute()` → `{total_documents, total_chunks, by_seguradora, documents}`.
- [app/infrastructure/repositories/faiss_repository.py](app/infrastructure/repositories/faiss_repository.py) — `FAISSVectorRepository`: pure vector ops. Composes `SQLiteMetadataStore`. `add` maps `c.metadata.ramo` into the entries dict (bug fix: previously omitted, causing chunks to always store "Desconhecido"). `search` returns `ramo` in `SearchResult`. `delete_all()` resets the FAISS index + truncates the `chunks` table — does not touch `documents`.
- [app/infrastructure/repositories/sqlite_metadata.py](app/infrastructure/repositories/sqlite_metadata.py) — `SQLiteMetadataStore`: `chunks` table with `COLLATE NOCASE` on `seguradora` and `ramo`. Manages `faiss_pos` renumbering after deletions. `update_document_metadata` patches seguradora/ano/tipo/ramo without touching embeddings. `truncate_all()` removes all rows; next `insert_many` restarts from `faiss_pos = 0`.
- [app/infrastructure/repositories/sqlite_catalog.py](app/infrastructure/repositories/sqlite_catalog.py) — `SQLiteDocumentCatalog`: `documents` table with `COLLATE NOCASE` on `seguradora` and `ramo`. Stores one row per PDF with `file_hash` (SHA-256 UNIQUE), `chunk_count`, `created_at`, `ramo`.
- [app/infrastructure/chunkers/semantic_chunker.py](app/infrastructure/chunkers/semantic_chunker.py) — `InsuranceSemanticChunker`. `_fixed_chunk` is marked as **Rust/PyO3 optimization target**. Module-level helpers: `_SECTION_TITLE_RE` (regex for Art., SEÇÃO, CAPÍTULO, CLÁUSULA, roman numerals, etc.), `_is_section_title(text)` (regex match OR all-caps ≥2-word heuristic ≤80 chars), `_apply_section_prefix(chunk_text, section_title)` (prepends `[SEÇÃO: <título>]\n`; skipped if the chunk already opens with the title). `_merge_segments` tracks `last_section` / `chunk_section` to inject the prefix into every output chunk.
- [app/infrastructure/gateways/deepseek_gateway.py](app/infrastructure/gateways/deepseek_gateway.py) — `DeepSeekGateway`: wraps `openai` SDK, owns the auditor system prompt (Chain-of-Thought, cross-reference resolution, formula transcription, ramo prioritisation). `_format_context` exposes `[Trecho N | Fonte | Ramo | Pág.]` headers so the model can filter by ramo. `max_tokens=4000`. `generate_stream` uses `stream=True` and yields raw token deltas — no retry loop (errors propagate to the route's SSE generator).
- [app/core/dependencies.py](app/core/dependencies.py) — single wiring point. Exposes `get_ask_use_case`, `get_ingest_use_case`, `get_inventory_use_case`, `get_vector_service`, `get_llm_service`, `get_document_catalog`.
- [ingest.py](ingest.py) — CLI bulk-ingestion de alta produtividade. Fluxo em 4 fases: coleta de metadados com auto-detect + session memory → resumo do lote com prévia de renomeação → renomeação física → indexação. Usa `get_ingest_use_case()` — caminho idêntico à API.
- [reindex.py](reindex.py) — re-indexação completa não-interativa. Exibe tabela de prévia com metadados auto-detectados pelo nome do arquivo, pede confirmação (ou `--yes`), apaga `faiss_index.bin` + `metadata.db` inteiros, depois indexa todos os PDFs de `--pdf-dir`. Import de `get_ingest_use_case` é deferido para após o wipe — garante que os `lru_cache` singletons sejam criados com os arquivos ausentes (índice vazio). Útil após mudanças no chunker que exigem re-embedding completo.
- [test_regression.py](test_regression.py) — script standalone de regressão de qualidade de recuperação (sem pytest). Chama `get_ask_use_case().execute()` diretamente com a query "carro reserva", `filter={"ramo": "Automovel"}`, `top_k=15`. Marca ✅ chunks que contêm termos-alvo, imprime tabela com rank/score/fonte/snippet. Exit 0 se ≥5 chunks relevantes, exit 1 caso contrário.
- [tests/test_semantic_chunker.py](tests/test_semantic_chunker.py) — 16 testes unitários para o chunker: `TestIsSectionTitle` (9 casos), `TestApplySectionPrefix` (3 casos), `TestInsuranceSemanticChunker` (4 casos de integração). Rode com `python -m pytest tests/`.

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

### /ask — SSE streaming

`POST /ask` is a **sync route** (`def`, not `async def`) that returns a `StreamingResponse` with `media_type="text/event-stream"`. FastAPI runs sync routes in a thread pool; Starlette iterates sync generators via `anyio` — both are correct for the fully-sync pipeline (FAISS → SQLite → OpenAI SDK).

Request body:
```json
{ "question": "...", "top_k": 15, "filter": {"seguradora": "Bradesco", "ramo": "Agricola"} }
```
`top_k` default 15, clamped 1–20. `filter` accepts any combination of `seguradora` and/or `ramo` — both optional. The FAISS search does a generic key-value match on all filter keys.

SSE event sequence:
```
data: {"type": "context", "data": [{text, source, page, seguradora, relevance_score}, ...]}\n\n
data: {"type": "text",    "data": "<token delta>"}\n\n   ← repeated per chunk
data: {"type": "no_context"}\n\n                          ← if FAISS returns no results
data: {"type": "error",   "data": "<message>"}\n\n        ← on LLM or pipeline exception
```

Headers sent: `Cache-Control: no-cache`, `X-Accel-Buffering: no` (prevents nginx/Render buffering).

Frontend SSE parser (`static/app.js`) splits on `/\r?\n\r?\n/` (handles LF and CRLF), finds the `data:` line inside each event block with `/^data:/`, strips the prefix with `replace(/^data:\s?/, '')`, then `JSON.parse`. Parse errors and handler errors are logged to `console.error` separately so they are visible in the browser DevTools console.

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

### Section-header injection (InsuranceSemanticChunker)

Tables and bullet lists have little own text and lose in semantic score against dense paragraphs. To fix this, every chunk produced by `_merge_segments` is prefixed with the last section title seen before the chunk:

```
[SEÇÃO: CLÁUSULA 5 – COBERTURAS]
| Cobertura | Limite |
| Incêndio  | 100%   |
```

Detection (`_is_section_title`): a segment is a title if its first line matches `_SECTION_TITLE_RE` (Art./Artigo N, SEÇÃO/CAPÍTULO/CLÁUSULA, COBERTURA/EXCLUSÃO/FRANQUIA, roman numerals II–VIIX, `N.N. Capital-letter`) **or** is a short all-caps line (≤ 80 chars, ≥ 2 words) such as `DISPOSIÇÕES GERAIS` or `AUTO RESERVA`.

No-duplicate rule: `_apply_section_prefix` skips the prefix when the chunk's first line already starts with the title — prevents the chunk that *is* the title from getting `[SEÇÃO: itself]`.

`_merge_segments` tracks two variables: `last_section` (updated on every title segment seen) and `chunk_section` (captured at the moment a new accumulated chunk begins). The prefix uses `chunk_section`, not `last_section`, so a chunk that starts before a title is not mislabelled with the title that came after.

**After any change to the chunker, run `python reindex.py` to regenerate all embeddings.** The dedup hash is file-content-based — unchanged PDFs would be skipped by `ingest.py`, but `reindex.py` wipes the index first, forcing a full re-embed.

### reindex.py — re-indexação completa

```bash
python reindex.py [--pdf-dir ./pdfs] [--yes]
```

Wipe-and-rebuild flow (no interactivity beyond confirmation):

```
1. Lista PDFs em --pdf-dir
2. Auto-detect seguradora/ramo/ano pelo nome do arquivo (mesma lógica do ingest.py)
3. Exibe tabela de prévia + avisos para metadados não detectados
4. Pede confirmação "s/N" (ou prossegue com --yes)
5. Apaga faiss_db/faiss_index.bin e faiss_db/metadata.db (chunks + documents)
6. Importa get_ingest_use_case() — lru_cache instancia repositórios do zero
7. Indexa cada PDF; relatório final lista sucessos e falhas
```

Fallbacks para metadados não detectáveis: seguradora → `"Desconhecida"`, ramo → `Ramo.DESCONHECIDO`, ano → `0`, tipo → `"Geral"`. Todos avisados na prévia.

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

### DeepSeek system prompt — estrutura e comportamento

O prompt vive em `_SYSTEM_PROMPT` dentro de [app/infrastructure/gateways/deepseek_gateway.py](app/infrastructure/gateways/deepseek_gateway.py). Principais blocos:

| Bloco | Propósito |
|---|---|
| **ESCOPO DE ATUAÇÃO** | Restringe o modelo a responder apenas sobre seguros |
| **ANÁLISE PRÉVIA SILENCIOSA** | Chain-of-Thought interno: mapeia cláusulas, referências cruzadas sumário↔conteúdo, fórmulas e ramo dominante antes de redigir |
| **FÓRMULAS E CÁLCULOS** | Obriga transcrição literal de fórmulas em Markdown; proíbe paráfrase |
| **PROIBIÇÃO DE DESCULPAS** | Impede "não encontrei" enquanto houver número de cláusula ou referência de página nos trechos |
| **FORMATO OBRIGATÓRIO** | 4 seções: Veredito Direto / Detalhes Técnicos / Letra Miúda / Prova Documental |

Parâmetros injetados dinamicamente no prompt: `{context}` (trechos formatados) e `{n_chunks}` (contagem real de trechos, usada nas instruções de exaustão).

Formato de cada trecho no contexto:
```
[Trecho N | Fonte: Bradesco | Ramo: Agricola | Pág. 47]:
<texto do chunk>
```

Configuração do modelo: `temperature=0.3`, `max_tokens=4000`, `timeout=30s`, `max_retries=3` (backoff exponencial 1s/2s).

### Observability

- `GET /metrics` — `{"queries_24h": N, "avg_retrieval_ms": X, "avg_llm_ms": Y, "avg_total_ms": Z}`
- `GET /stats` — includes `"inventory": {"total_documents": N, "total_chunks": N}`
- Structured JSON logs to stdout:
  - `"SSE stream iniciado | pergunta='...' top_k=N filter=..."` — emitted when the stream generator starts
  - `"Filtro recebido via UI: ..."` — emitted at route entry before the generator starts
  - `{"event": "query", "total_ms": ..., "top_k": N, "chunks_returned": K, "filter": ..., "document_type": ...}`
  - `{"event": "query_no_context", "top_k": N, "filter": ..., "document_type": ...}`
  - `"Erro no streaming LLM: ..."` / `"Erro no SSE stream: ..."` — with full traceback (`exc_info=True`)
- `LOG_LEVEL=DEBUG` exposes recall logs from the use case:
  - `"Retrieval: M chunks retornados pelo FAISS."` (M = top_k × 4)
  - `"Reranking: M avaliados, top K retidos para o LLM."`
- `LOG_LEVEL` env var controls verbosity (default `INFO`)

### UI filters (static/index.html + static/app.js)

Two `<select>` dropdowns above the chat input let the user narrow the search before sending a question:

| Dropdown | Element ID | Values |
|---|---|---|
| Seguradora | `seguradora-filter` | Todas, Bradesco, Allianz, Porto Seguro, Azul, Tokio Marine, Liberty, Mapfre |
| Ramo | `ramo-filter` | Todos, Agricola, Automovel, PME, Construcao Civil, Residencial |

`sendQuestion` builds the `filter` object incrementally — only adds a key when the value is non-empty — so selecting "Todas / Todos" sends no filter at all. Both keys can be combined freely.