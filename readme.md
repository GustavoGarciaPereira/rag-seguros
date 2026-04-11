# 🛡️ Help Corretor — Auditor IA para Seguros

**Help Corretor** é uma plataforma de inteligência artificial baseada em **RAG (Retrieval-Augmented Generation)** projetada para transformar manuais de seguros complexos em respostas auditáveis, rápidas e precisas.

Diferente de um chatbot comum, este sistema atua como um **Auditor Técnico**, utilizando uma "Análise Prévia Silenciosa" (Chain-of-Thought) para cruzar dados de sumários, cláusulas e fórmulas matemáticas, garantindo que a "letra miúda" nunca seja ignorada.

---

## ✨ Principais Funcionalidades

* **Busca por Contexto Profundo:** Recuperação de até 15 trechos relevantes com Re-ranking híbrido.
* **Filtros Inteligentes:** Seleção por **Seguradora** e **Ramo** (Agrícola, Automóvel, PME, etc.) diretamente na UI.
* **Resposta em Streaming (SSE):** Visualização em tempo real conforme a IA gera a análise, com fontes exibidas instantaneamente.
* **Motor de Auditoria:**
    * **Veredito Direto:** Resposta curta e grossa no início.
    * **Transcrição de Fórmulas:** Extração literal de cálculos de rateio e indenização.
    * **Prova Documental:** Citação direta de fonte e página `[Bradesco | Pág. 47]`.
* **CLI de Alta Produtividade:** Script `ingest.py` com auto-detecção de metadados e renomeação determinística de arquivos.

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
git clone https://github.com/GustavoGarciaPereira/mvp-seguros-rag.git
cd mvp-seguros-rag
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

---

## 📂 Fluxo de Ingestão de Manuais

Para garantir a precisão, o sistema utiliza um fluxo de ingestão semi-automático via CLI:

1.  Coloque os PDFs brutos em `./pdfs/`.
2.  Execute o assistente: `python ingest.py`.
3.  O script irá:
    * **Auto-detectar** Seguradora e Ramo pelo nome do arquivo.
    * **Renomear** o arquivo para um padrão auditável: `Bradesco_Agricola_Geral_2025_559ae.pdf`.
    * **Indexar** os chunks com sobreposição semântica no banco local.

> **Importante:** No plano gratuito do Render, o banco `faiss_db/` deve ser commitado no repositório, pois o disco é efêmero.

---

## 🧠 Arquitetura: O "Cérebro" do Auditor

O sistema utiliza **Clean Architecture**, separando regras de negócio (Use Cases) de detalhes de implementação (Gateways/Repositories).

### A Lógica de Resposta
A IA é instruída a seguir um protocolo de 4 etapas antes de responder:
1.  **Mapeamento:** Identificar todas as cláusulas e números de páginas nos 15 trechos.
2.  **Cruzamento:** Se o sumário cita "Cláusula 128", ela busca o conteúdo dessa cláusula nos demais chunks.
3.  **Cálculo:** Se houver fórmulas (ex: Rateio Parcial), elas são transcritas integralmente em Markdown/LaTeX.
4.  **Verificação de Ramo:** Priorizar informações que batam com o `ramo` filtrado pelo usuário.

---

## 📈 Endpoints Principais

* `GET /`: Interface Web do Assistente.
* `POST /ask`: Endpoint de RAG com Streaming SSE.
* `GET /stats`: Inventário de documentos e status do índice.
* `GET /metrics`: Latências de busca e geração das últimas 24h.
* `POST /admin/upload`: Ingestão de novos manuais via API (requer `X-Admin-Key`).

---

## 📝 Licença e Autor

Projeto desenvolvido por **Gustavo Garcia Pereira**.
Focado em aplicar Inteligência Artificial para resolver problemas reais do mercado de seguros brasileiro.