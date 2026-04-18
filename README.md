# 🛡️ Help Corretor — Auditor IA para Seguros

**Help Corretor** é uma plataforma de inteligência artificial baseada em **RAG (Retrieval-Augmented Generation)** projetada para transformar manuais de seguros complexos em respostas auditáveis, rápidas e precisas.

Diferente de um chatbot comum, este sistema atua como um **Auditor Técnico**, utilizando uma "Análise Prévia Silenciosa" (Chain-of-Thought) para cruzar dados de sumários, cláusulas e fórmulas matemáticas, garantindo que a "letra miúda" nunca seja ignorada.

---

## ✨ Principais Funcionalidades

* **Busca por Contexto Profundo:** Recuperação de até 15 trechos relevantes com re-ranking híbrido (70% semântico + 30% léxico).
* **Section-Header Injection:** Cada chunk é prefixado com o título da seção pai (`[SEÇÃO: AUTO RESERVA]`), eliminando falsos negativos em tabelas e listas esparsas.
* **Filtros Inteligentes:** Seleção por **Seguradora** e **Ramo** (Agrícola, Automóvel, PME, etc.) diretamente na UI.
* **Resposta em Streaming (SSE):** Visualização em tempo real conforme a IA gera a análise, com fontes exibidas instantaneamente.
* **Motor de Auditoria:**
    * **Veredito Direto:** Resposta objetiva no início.
    * **Transcrição de Fórmulas:** Extração literal de cálculos de rateio e indenização em Markdown.
    * **Prova Documental:** Citação direta de fonte e página `[Bradesco | Pág. 47]`.
* **CLI de Alta Produtividade:** Script `ingest.py` com auto-detecção de metadados e renomeação determinística de arquivos.
* **Re-indexação Completa:** Script `reindex.py` para wipe + rebuild após mudanças no chunker.

---

## 🛠️ Stack Tecnológica

| Camada | Tecnologia |
| :--- | :--- |
| **Backend** | FastAPI (Python 3.11) |
| **LLM** | DeepSeek-V3 (via SSE Streaming) |
| **Vetorização** | Sentence-Transformers (`all-MiniLM-L6-v2`) |
| **Banco de Dados** | FAISS (Vetores) + SQLite (Metadados) |
| **Frontend** | Vanilla JS + Tailwind CSS + Marked.js |
| **Infra** | Docker + Render (Otimizado para 512MB RAM) |

---

## 🚀 Como Rodar Localmente

### 1. Preparação
```bash
git clone https://github.com/GustavoGarciaPereira/rag-seguros.git
cd rag-seguros
cp .env.example .env # Adicione suas chaves DEEPSEEK_API_KEY e ADMIN_API_KEY
```

### 2. Com Docker (Recomendado)
```bash
docker compose up --build
```

### 3. Sem Docker
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

O servidor sobe em `http://localhost:8000`. Documentação da API disponível em `/docs`.

---

## 📂 Fluxo de Ingestão de Manuais

Para garantir a precisão, o sistema utiliza um fluxo de ingestão semi-automático via CLI:

1. Coloque os PDFs brutos em `./pdfs/`.
2. Execute o assistente interativo: `python ingest.py`
3. O script irá:
    * **Auto-detectar** Seguradora, Ramo e Ano pelo nome do arquivo.
    * **Renomear** para um padrão auditável: `Bradesco_Agricola_Geral_2025_559ae.pdf`.
    * **Indexar** os chunks com sobreposição semântica e section-header injection.

Para re-indexar tudo do zero (ex: após mudanças no chunker):
```bash
python reindex.py --pdf-dir ./pdfs
```

> **Importante:** No plano gratuito do Render, o banco `faiss_db/` deve ser commitado no repositório, pois o disco é efêmero. Após qualquer `reindex.py`, commite os binários em commit separado.

---

## 🧠 Arquitetura: O "Cérebro" do Auditor

O sistema utiliza **Clean Architecture**, separando regras de negócio (Use Cases) de detalhes de implementação (Gateways/Repositories).

### Pipeline RAG

```
PDF Upload → PdfDocumentParser (pypdf)
          → InsuranceSemanticChunker (1200 chars, overlap 200, section-header injection)
          → SHA-256 dedup (IngestDocument)
          → FAISSVectorRepository (all-MiniLM-L6-v2, 384-dim)

Query     → FAISS fetch_k=60 (top_k × 4)
          → KeywordOverlapReranker (70% semântico + 30% léxico PT)
          → slice top_k=15
          → DeepSeekGateway (SSE streaming)
```

### Section-Header Injection

Tabelas e listas têm pouco texto próprio e perdem no score semântico para parágrafos densos. Para resolver isso, cada chunk recebe o prefixo com o último cabeçalho de seção visto:

```
[SEÇÃO: AUTO RESERVA]
| Plano    | Diárias | Veículo          |
| Básico   | 7       | Popular 1.0      |
| Plus     | 15      | Completo 1.0T    |
| Premium  | 30      | Porte médio 1.6  |
```

Resultado do teste de regressão após a implementação: **13/15 chunks relevantes** para a query "carro reserva (Básico, Plus, Premium)".

### A Lógica de Resposta

A IA segue um protocolo de 4 etapas antes de redigir:

1. **Mapeamento:** Identifica todas as cláusulas e páginas nos chunks recebidos.
2. **Cruzamento:** Se o sumário cita "Cláusula 128", busca o conteúdo dessa cláusula nos demais chunks.
3. **Cálculo:** Fórmulas (ex: Rateio Parcial, VMR × Fator FIPE) são transcritas integralmente em Markdown.
4. **Verificação de Ramo:** Prioriza informações que correspondam ao `ramo` filtrado, evitando contaminação semântica entre ramos distintos.

---

## 🧪 Qualidade e Testes

```bash
# Teste de regressão de qualidade de recuperação (sem pytest)
python test_regression.py
# Exit 0 = ≥5/15 chunks relevantes para query "carro reserva" com ramo=Automovel

# Teste de regressão de qualidade das respostas (estrutural)
python test_regression_answers.py
# Exit 0 = respostas atendem aos critérios de seções e tamanho mínimo

# Testes unitários do chunker
python -m pytest tests/
# 16 testes: _is_section_title, _apply_section_prefix, integração
```

---

## 📈 Endpoints Principais

| Método | Rota | Descrição |
| :--- | :--- | :--- |
| `GET` | `/` | Interface Web do Assistente |
| `POST` | `/ask` | RAG com Streaming SSE |
| `GET` | `/stats` | Inventário de documentos e status do índice |
| `GET` | `/metrics` | Latências de busca e geração das últimas 24h |
| `GET` | `/api/inventory` | Catálogo agrupado por seguradora |
| `POST` | `/admin/upload` | Ingestão via API (requer `X-Admin-Key`) |

### Exemplo de request `/ask`

```json
{
  "question": "Quais são as opções de carro reserva e como funcionam as diárias?",
  "top_k": 15,
  "filter": { "seguradora": "Bradesco", "ramo": "Automovel" }
}
```

`filter` aceita qualquer combinação de `seguradora` e/ou `ramo` — ambos opcionais.

---

## 📝 Licença e Autor

Projeto desenvolvido por **Gustavo Garcia Pereira**.
Focado em aplicar Inteligência Artificial para resolver problemas reais do mercado de seguros brasileiro.