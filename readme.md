# Help Corretor — Auditor IA para Seguros

**Help Corretor** e uma plataforma de inteligencia artificial baseada em **RAG (Retrieval-Augmented Generation)** projetada para centralizar o conhecimento tecnico de diversas seguradoras em uma interface unica, agil e auditavel.

A ferramenta permite que colaboradores de corretoras consultem coberturas, limites e clausulas complexas de manuais (PDFs) com precisao cirurgica, eliminando a necessidade de navegar em multiplos portais.

---

## Stack Tecnologica

| Tecnologia | Funcao |
| --- | --- |
| **FastAPI** | Backend de alta performance |
| **FAISS (CPU)** | Banco de dados vetorial local |
| **Sentence-Transformers** | Embeddings (`all-MiniLM-L6-v2`) |
| **DeepSeek API** | LLM (OpenAI-compatible) para geracao de respostas |
| **Docker** | Empacotamento e deploy |

---

## Variaveis de Ambiente

Crie um arquivo `.env` na raiz do projeto (use `.env.example` como base):

| Variavel | Obrigatoria | Descricao |
| --- | --- | --- |
| `DEEPSEEK_API_KEY` | Sim | Chave de API da DeepSeek |
| `ADMIN_API_KEY` | Sim | Chave secreta para `POST /admin/upload` |
| `LOG_LEVEL` | Nao | Nivel de log (`INFO` por padrao) |

Gere uma chave `ADMIN_API_KEY` segura:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## Rodar Localmente com Docker

**Pre-requisitos:** Docker e Docker Compose instalados.

```bash
# 1. Clone o repositorio
git clone https://github.com/GustavoGarciaPereira/mvp-seguros-rag.git
cd mvp-seguros-rag

# 2. Configure as variaveis de ambiente
cp .env.example .env
# Edite .env com suas chaves reais

# 3. Suba o servico
docker compose up --build

# A API estara disponivel em http://localhost:8000
```

O volume `./faiss_db` e montado no container, persistindo o indice FAISS entre restarts locais.

### Rodar sem Docker (ambiente virtual)

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # edite com suas chaves
python run.py
```

---

## Fluxo de Ingestao (Recomendado para Producao)

O Render gratuito tem 512MB de RAM — insuficiente para indexar PDFs grandes em tempo real.
A solucao e **indexar localmente** e commitar o `faiss_db/` gerado.

### Passo a passo

**1. Coloque os PDFs na pasta `./pdfs/`** (ignorada pelo git):
```bash
mkdir pdfs
cp seus-documentos/*.pdf pdfs/
```

**2. Execute o script de ingestao:**
```bash
python ingest.py
# Para uma pasta diferente:
python ingest.py --pdf-dir ./minha-pasta
```

O script pede os metadados de cada PDF interativamente:
```
--- bradesco-auto-2024.pdf ---
Seguradoras disponíveis: Bradesco, Porto Seguro, Azul, ...
  Seguradora: Bradesco
  Ano (ex: 2024): 2024
  Tipo (ex: Geral, Auto, Vida) [Geral]: Auto
  OK — 312 chunks indexados

==================================================
Resumo: 1 documento(s), 312 chunks indexados
Índice salvo em: ./faiss_db
```

**3. Comite o indice e faca deploy:**
```bash
git add faiss_db/
git commit -m "atualiza indice FAISS"
git push
```

O Render detecta o push e faz o deploy automaticamente. O indice
pre-construido ja estara disponivel quando o container subir.

**4. Em producao, desabilite o upload no dashboard do Render:**

Adicione a variavel de ambiente `ENABLE_UPLOAD=false` — isso retorna
403 nos endpoints `/upload` e `/admin/upload`, evitando tentativas
de upload que causariam OOM no servidor.

---

## Deploy no Render (plano gratuito)

### Passo a passo

1. **Fork** este repositorio para sua conta do GitHub.

2. Acesse [render.com](https://render.com) e faca login.

3. Clique em **New > Web Service**.

4. Conecte o repositorio forkado e selecione **Docker** como runtime (o `render.yaml` ja configura isso automaticamente se voce usar **New > Blueprint**).

5. Em **Environment Variables**, adicione:
   - `DEEPSEEK_API_KEY` — sua chave da DeepSeek
   - `ADMIN_API_KEY` — chave secreta gerada localmente

6. Clique em **Deploy**. O primeiro build leva alguns minutos (instalacao de dependencias pesadas como faiss e sentence-transformers).

7. Apos o deploy, acesse a URL publica fornecida pelo Render. O healthcheck em `/health` sera verificado automaticamente.

### Usando render.yaml (Blueprint)

O arquivo `render.yaml` na raiz do repositorio descreve o servico como Infrastructure as Code. Para usa-lo:

1. No Render, clique em **New > Blueprint**.
2. Conecte o repositorio — o Render detectara o `render.yaml` automaticamente.
3. Defina os valores de `DEEPSEEK_API_KEY` e `ADMIN_API_KEY` quando solicitado.

---

## Limitacoes do Plano Gratuito do Render

> **Sem persistencia de disco:** O indice FAISS (`faiss_db/`) e armazenado no sistema de arquivos efemero do container. A cada deploy ou restart, o indice e perdido e os documentos precisam ser reenviados via `/upload` ou `/admin/upload`.
>
> **Sleep apos inatividade:** O servico dorme apos 15 minutos sem requisicoes. O primeiro request apos o sleep pode demorar **ate 30 segundos** enquanto o container reinicia.
>
> **Para persistencia real em producao**, use uma das alternativas:
> - **Render Disk** (pago) montado em `/app/faiss_db`
> - Vector store gerenciado: Pinecone, Qdrant Cloud ou similar

---

## Endpoints da API

| Metodo | Endpoint | Descricao |
| --- | --- | --- |
| `GET` | `/` | Interface web |
| `GET` | `/health` | Healthcheck |
| `GET` | `/status` | Verifica se ha documentos indexados |
| `POST` | `/upload` | Upload publico de PDF |
| `POST` | `/admin/upload` | Upload com validacao (requer `X-Admin-Key`) |
| `POST` | `/ask` | Pergunta sobre os documentos |
| `GET` | `/stats` | Estatisticas do sistema |
| `GET` | `/metrics` | Metricas operacionais (latencias 24h) |

---

## Arquitetura

1. **Ingestao:** Upload de PDFs com metadados (seguradora, ano, tipo).
2. **Fragmentacao semantica:** Chunks de 1200 chars com overlap de 200, respeitando limites de clausulas.
3. **Vetorizacao:** `all-MiniLM-L6-v2` (384 dims) + FAISS `IndexFlatL2`.
4. **Consulta:** Top-K=10 com reranking hibrido (70% FAISS + 30% sobreposicao de termos).
5. **Geracao:** DeepSeek `deepseek-chat` com prompt estruturado em 4 secoes (Veredito, Detalhes, Letra Miuda, Prova Documental).

---

## Roadmap

- [x] Suporte multi-seguradora com filtros por metadados
- [x] Citacoes com pagina de origem `[Seguradora | Pag. X]`
- [x] Chunking semantico por clausulas
- [x] Reranking hibrido
- [x] Metricas operacionais (`/metrics`)
- [x] Deploy Docker / Render
- [ ] Painel de inventario de manuais ativos
- [ ] Backup automatizado do indice FAISS para Cloud Storage
- [ ] Exportacao de relatorio de auditoria em PDF

---

**Feito por Gustavo Garcia Pereira**
