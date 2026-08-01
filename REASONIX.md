# REASONIX.md — Help Corretor (Auditor IA para Seguros)

Projeto RAG (Retrieval-Augmented Generation) para análise de manuais de seguros. Usa **FAISS + Sentence-Transformers** para busca vetorial com re-ranking híbrido e **DeepSeek (deepseek-v4-pro, configurável via `DEEPSEEK_MODEL`)** como LLM via streaming SSE. Backend **FastAPI**, frontend **Vanilla JS + Tailwind**, infra **Docker / Render (512 MB RAM)**. Inclui **memória de sessão** com histórico persistido em SQLite.

## Comandos

```bash
# Instalar dependências (runtime)
pip install -r requirements.txt

# Instalar dependências de desenvolvimento/teste (pytest etc.)
pip install -r requirements-dev.txt

# Rodar servidor com auto-reload
python run.py

# Ingestão interativa de PDFs (coleta metadados, renomeia, indexa)
python ingest.py [--pdf-dir ./pdfs]

# Wipe total do índice e re-indexação (não-interativo com --yes)
python reindex.py [--pdf-dir ./pdfs] [--yes]

# Testes unitários do chunker
python -m pytest tests/

# Regressão de qualidade de recuperação (sem LLM, exit 0 = pass)
python tests/test_regression_retrieval.py

# Regressão estrutural de respostas (chama LLM, exit 0 = pass)
python tests/test_regression_answers.py

# Testes unitários de histórico de chat
python -m pytest tests/test_chat_history.py -v

# Teste de integração de memória de sessão
python tests/test_chat_memory.py

# Docker
docker compose up --build
```

O servidor sobe em `http://localhost:8000`. Docs da API em `/docs`.

## Variáveis de ambiente (.env)

| Variável | Obrigatória | Descrição |
|---|---|---|
| `DEEPSEEK_API_KEY` | Sim | Chave da API DeepSeek |
| `ADMIN_API_KEY` | Sim | Segredo para `POST /admin/upload` |
| `DEEPSEEK_MODEL` | Não | Modelo DeepSeek (default `deepseek-v4-pro`) |
| `LOG_LEVEL` | Não | `DEBUG` / `INFO` / `WARNING` / `ERROR` (default `INFO`) |
| `ENABLE_UPLOAD` | Não | Habilita endpoints de upload (default `true`) |

## Arquitetura — Clean Architecture

O projeto segue Clean Architecture em 4 camadas dentro de `app/`:

| Camada | Path | Responsabilidade |
|---|---|---|
| **Domain** | `app/domain/` | Entidades puras, value objects, enums e interfaces abstratas — zero I/O |
| **Use Cases** | `app/use_cases/` | Orquestração da lógica de negócio via interfaces injetadas |
| **Infrastructure** | `app/infrastructure/` | Implementações concretas (FAISS, SQLite, pypdf, DeepSeek) |
| **API** | `app/api/` | Rotas FastAPI — apenas HTTP, delega para use cases |

### Injeção de dependências (`app/core/dependencies.py`)

Todas as dependências são montadas via singletons `lru_cache` e injetadas nas rotas com `Depends`:

```python
def get_ask_use_case() -> AskInsuranceQuestion:
    return AskInsuranceQuestion(_vector_repo(), _reranker(), _llm_gateway())

def get_ingest_use_case() -> IngestDocument:
    return IngestDocument(_parser(), _chunker(), _vector_repo(), _document_catalog())

def get_inventory_use_case() -> GetInventory:
    return GetInventory(_document_catalog())
```

### Arquivos-chave

- `app/domain/entities/insurance.py` — `Seguradora`, `Ramo`, `DocumentType` (str Enums). `Seguradora.allowed_for_admin()` retorna a allowlist.
- `app/domain/entities/document.py` — `InsuranceMetadata` (VO), `Chunk`, `SearchResult`, `ParsedPage`, `DocumentRecord`
- `app/domain/interfaces/vector_repository.py` — `VectorRepository` ABC: `add`, `search`, `delete`, `update_metadata`, `has_document`, `count`
- `app/domain/interfaces/document_catalog.py` — `DocumentCatalog` ABC: `register`, `find_by_hash`, `update_metadata`, `remove`, `list_all`, `total_chunks`
- `app/domain/interfaces/llm_gateway.py` — `LLMGateway` ABC: `generate` (sync) + `generate_stream` (Iterator[str])
- `app/use_cases/ingest_document.py` — `IngestDocument.execute()`: parse → chunk → SHA-256 dedup → embed → catalog
- `app/use_cases/answer_question.py` — `AskInsuranceQuestion`: FAISS fetch_k=top_k×4 → reranker → slice top_k → DeepSeek. Dois métodos: `execute()` (sync) e `execute_stream()` (SSE). Injeta histórico de sessão no prompt e persiste Q&A após resposta.
- `app/use_cases/get_inventory.py` — `GetInventory.execute()`: catálogo agrupado por seguradora
- `app/infrastructure/repositories/faiss_repository.py` — `FAISSVectorRepository`: opera FAISS + compõe `SQLiteMetadataStore`
- `app/infrastructure/repositories/sqlite_metadata.py` — `SQLiteMetadataStore`: tabela `chunks` com `COLLATE NOCASE`
- `app/infrastructure/repositories/sqlite_catalog.py` — `SQLiteDocumentCatalog`: tabela `documents` com `file_hash UNIQUE`
- `app/infrastructure/chunkers/semantic_chunker.py` — `InsuranceSemanticChunker`: 1200-char target, 200-char overlap, section-header injection
- `app/infrastructure/rerankers/keyword_reranker.py` — `KeywordOverlapReranker`: 70% semântico + 30% léxico PT + `_DOMAIN_EXPANSIONS`
- `app/infrastructure/gateways/deepseek_gateway.py` — `DeepSeekGateway`: wrapping OpenAI SDK, system prompt do auditor, `max_tokens=4000`, SSE streaming
- `app/api/routes/ask.py` — `POST /ask` (SSE stream)
- `app/api/routes/upload.py` — `POST /upload`, `POST /admin/upload`
- `app/api/routes/inventory.py` — `GET /api/inventory`
- `app/api/routes/health.py` — `GET /`, `/health`, `/status`, `/stats`, `/metrics`
- `app/core/config.py` — `Settings` (pydantic-settings), deriva allowlists dos enums de domínio; inclui `DEEPSEEK_MODEL`
- `app/core/logging.py` — `_JsonFormatter` + `setup_logging()`
- `app/domain/interfaces/chat_history.py` — `ChatHistory` ABC: `add_message`, `get_recent_messages`
- `app/infrastructure/repositories/sqlite_chat_history.py` — `SQLiteChatHistory`: implementação thread-safe em `faiss_db/chat_history.db`
- `app/core/metrics.py` — `MetricsStore` in-memory (latências 24h)
- `app/main.py` — App FastAPI, CORS, `/static` mount, routers, warm-up no startup

## Pipeline RAG

```
PDF Upload → PdfDocumentParser (pypdf)
          → InsuranceSemanticChunker (1200 chars, overlap 200, section-header injection)
          → SHA-256 dedup (IngestDocument)
          → FAISSVectorRepository (all-MiniLM-L6-v2, 384-dim)

Query     → FAISS fetch_k=60 (top_k × 4)
          → KeywordOverlapReranker (70% semântico + 30% léxico PT)
          → slice top_k=15
          → DeepSeekGateway (SSE streaming, temperature=0.3, max_tokens=4000)
```

## Persistência FAISS + SQLite

Arquivos em `faiss_db/` (commitados no repo — Render free-tier não tem disco persistente):

- `faiss_index.bin` — índice FAISS (vetores)
- `metadata.db` — SQLite com tabelas `chunks` e `documents`

Após qualquer mudança no chunker, execute `python reindex.py` para regenerar todos os embeddings. O `ingest.py` faria skip por SHA-256 se o PDF não mudou, mas o `reindex.py` dá wipe first.

## Section-Header Injection

Cada chunk recebe prefixo com o último cabeçalho de seção: `[SEÇÃO: CLÁUSULA 5 – COBERTURAS]\n`. Detecta títulos por regex (`Art.`, `SEÇÃO`, `CLÁUSULA`, etc.) ou heurística all-caps (≤80 chars, ≥2 palavras). Não duplica se o chunk já começa com o título.

## Enums de Ramo

| Valor | Descrição |
|---|---|
| `Agricola` | Seguro agrícola/rural |
| `Automovel` | Seguro de automóvel |
| `PME` | Pequenas e médias empresas |
| `Construcao Civil` | Riscos de engenharia |
| `Residencial` | Seguro residencial |
| `Desconhecido` | Padrão quando não identificado |

## Endpoints da API

| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/` | Interface web |
| `GET` | `/health` | Status do vector store |
| `GET` | `/status` | `{total_chunks, ready}` |
| `GET` | `/stats` | Inventário + conectividade LLM |
| `GET` | `/metrics` | Latências 24h |
| `POST` | `/upload` | Upload aberto |
| `POST` | `/admin/upload` | Upload admin (requer `X-Admin-Key`) |
| `POST` | `/ask` | RAG com streaming SSE |
| `GET` | `/api/inventory` | Catálogo agrupado por seguradora |

## SSE Streaming (`POST /ask`)

Rota sync (`def`, não `async def`) retornando `StreamingResponse` com `text/event-stream`. Eventos:

```
data: {"type": "session",  "data": "<uuid>"}\n\n     ← sempre o primeiro evento
data: {"type": "context",  "data": [...]}\n\n
data: {"type": "text",     "data": "<token>"}\n\n    ← repetido por chunk
data: {"type": "no_context"}\n\n
data: {"type": "error",    "data": "<msg>"}\n\n
```

Headers: `Cache-Control: no-cache`, `X-Accel-Buffering: no`.

## Chat Memory (Memória de Sessão)

Sistema de histórico de conversas com sessões identificadas por UUID.

**Fluxo:**
1. Frontend gera `session_id` (UUID v4) no carregamento da página
2. Envia `session_id` em cada `POST /ask`
3. Se omitido, servidor gera UUID e emite `{"type": "session", "data": "<uuid>"}` como primeiro evento SSE
4. Use case injeta as últimas 10 mensagens (5 trocas) no prompt do LLM
5. Após o stream terminar, pergunta + resposta são persistidas

**Persistência:** `SQLiteChatHistory` em `faiss_db/chat_history.db` (separado do `metadata.db`; **não versionado no git** — conversas são dados, não código).
Tabela `messages`: `id`, `session_id`, `role` (`user`|`assistant`), `content`, `created_at`.

**Truncagem:** Por quantidade (últimas 10 mensagens), sem contagem de tokens.

**Limitação:** Disco efêmero no Render free-tier → histórico perdido em deploys.

## Deduplicação (IngestDocument)

```
SHA-256(file) → catalog.find_by_hash()
  ├─ not found          → full ingest (parse → chunk → embed → add → register)
  ├─ found, same meta   → skip (retorna chunk_count existente)
  └─ found, diff meta   → update_metadata in-place (sem re-embed)
```

## ingest.py — CLI de 4 fases

1. **Coleta de metadados**: auto-detect por substring normalizada no nome do arquivo + session memory
2. **Resumo do lote**: tabela + prévia de renomeação, confirmação S/n
3. **Renomeação física**: `{Seguradora}_{Ramo}_{Tipo}_{Ano}_{suffix5}.pdf` (suffix = 5 hex do SHA-1 do stem original)
4. **Indexação**: usa `get_ingest_use_case()` (caminho idêntico à API)

## reindex.py — Re-indexação completa

1. Lista PDFs → auto-detect metadados → exibe tabela de prévia
2. Confirmação (ou `--yes`)
3. Apaga `faiss_index.bin` + `metadata.db`
4. Importa `get_ingest_use_case()` (lru_cache instancia do zero com índice vazio)
5. Indexa cada PDF → relatório final

Metadados não detectáveis: seguradora → `"Desconhecida"`, ramo → `Ramo.DESCONHECIDO`, ano → `0`, tipo → `"Geral"`.

## DeepSeek System Prompt

Prompt vive em `_SYSTEM_PROMPT` dentro de `deepseek_gateway.py`. Estrutura da resposta:

1. **Veredito Direto** — resposta objetiva
2. **Detalhes Técnicos** — coberturas (o que cobre / limites / não cobre), comparação entre seguradoras, fórmulas
3. **Letra Miúda** — cláusulas, exclusões, franquias
4. **Prova Documental** — citação `[Fonte | Pág. N]`

Regras condicionais importantes:
- Coberturas → sempre organizar em "O que cobre → Limites → O que não cobre"
- Múltiplas seguradoras sem filtro → comparação explícita lado a lado
- Allianz + 0km → mencionar **180 dias** explicitamente

## KeywordOverlapReranker — Expansões de domínio

`_DOMAIN_EXPANSIONS` mapeia termos da query a sinônimos:

| Query | Expansão |
|---|---|
| `perda` / `indenização` | vmr, fipe, 0km, 180, 365 |
| `total` | 0km, zero quilômetro, 180, 365, vmr |
| `carro` | veículo, automóvel, reserva, locação |
| `reserva` | carro, locação, diárias, básico, plus, premium |
| `franquia` | dedutível, participação, obrigatória |
| `cobertura` | cláusula, assistência, incluído, compreendido |

## Testes

| Arquivo | O que testa | Framework |
|---|---|---|
| `tests/test_semantic_chunker.py` | 16 testes unitários: `_is_section_title`, `_apply_section_prefix`, integração | pytest |
| `tests/test_keyword_reranker.py` | 10 testes unitários: domínio, scores, pesos, edge cases | pytest |
| `tests/test_chat_history.py` | CRUD de mensagens, isolamento de sessão, limite | pytest |
| `tests/test_regression_retrieval.py` | Qualidade de recuperação: >=5/15 chunks relevantes para "carro reserva" com ramo=Automovel | pytest + standalone |
| `tests/test_regression_answers.py` | Qualidade estrutural das respostas: seções obrigatórias, termos requeridos, tamanho minimo | pytest (slow) + standalone |

## CI (GitHub Actions)

Workflow em `.github/workflows/test.yml`: `push`/`PR` para `main`, dois jobs independentes (`test-retrieval` e `test-answers`). Ambos verificam `DEEPSEEK_API_KEY` antes de rodar.

## Observabilidade

- Logs JSON estruturados para stdout com eventos `query`, `query_no_context`, erros com traceback
- `GET /metrics` → `{queries_24h, avg_retrieval_ms, avg_llm_ms, avg_total_ms}`
- `LOG_LEVEL=DEBUG` expõe logs de recall: contagem de candidatos FAISS, reranking, `faiss_pos` com `OK/SKIP` por filtro

## Cuidados / Convenções

- **Nunca commitar sem perguntar ao usuário antes** (regra do projeto)
- `faiss_db/` é commitado no repo — após `reindex.py`, commitar os binários em commit separado
- Após qualquer mudança no chunker → `python reindex.py` obrigatório (ingest.py faria skip por SHA-256)
- `lru_cache` nos singletons de `dependencies.py`: em `reindex.py`, o import é deferido para após o wipe do índice
- `COLLATE NOCASE` em `seguradora` e `ramo` nas tabelas SQLite; `.lower()` no lado Python para consistência
- Rotas sync (`def`) com `StreamingResponse` — correto porque todo o pipeline é sync (FAISS, SQLite, OpenAI SDK)
- Endpoints de upload podem causar OOM no Render gratuito — usar `ENABLE_UPLOAD=false` em produção com índice pré-construído
- Modelo de embeddings pré-baixado na imagem Docker (`HF_HOME=/app/model_cache`) para evitar cold start de ~60s
