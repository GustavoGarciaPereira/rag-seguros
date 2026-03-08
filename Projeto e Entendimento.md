# Chat Conversation

Note: _This is purely the output of the chat conversation and does not contain any raw data, codebase snippets, etc. used to generate the output._

### User Input

leia o projete e entenda

*Listed directory [mvp-seguros-rag](file:///home/gustavo/statistica_gado/mvp-seguros-rag) *

*Viewed [requirements.txt](file:///home/gustavo/statistica_gado/mvp-seguros-rag/requirements.txt) *

*Viewed [main.py](file:///home/gustavo/statistica_gado/mvp-seguros-rag/main.py) *

*Viewed [run.py](file:///home/gustavo/statistica_gado/mvp-seguros-rag/run.py) *

*Viewed [llm_service.py](file:///home/gustavo/statistica_gado/mvp-seguros-rag/llm_service.py) *

*Viewed [vector_store_faiss.py](file:///home/gustavo/statistica_gado/mvp-seguros-rag/vector_store_faiss.py) *

### Planner Response

O projeto **"Bradesco Insurance RAG Assistant"** (MVP Seguros RAG) é uma aplicação web projetada para ajudar usuários a analisar e tirar dúvidas sobre apólices de seguro (especificamente do Bradesco) utilizando Inteligência Artificial Generativa com a técnica RAG (Retrieval-Augmented Generation).

Aqui está um resumo detalhado do que encontrei:

### 1. Objetivo
Permitir que o usuário faça o upload de arquivos PDF (condições gerais, apólices, manuais) e faça perguntas em linguagem natural. O sistema busca os trechos mais relevantes nos documentos processados e usa uma IA (DeepSeek) para gerar a resposta precisa.

### 2. Arquitetura e Tecnologias
O projeto é construído em **Python** e utiliza as seguintes tecnologias principais:

*   **API / Backend:**
    *   **FastAPI:** Framework web moderno e rápido.
    *   **Uvicorn:** Servidor ASGI para rodar a aplicação.
*   **Processamento de Documentos:**
    *   **pypdf:** Para extração de texto dos arquivos PDF transportados.
*   **Inteligência Artificial (RAG):**
    *   **Vector Store (FAISS):** Utiliza o `faiss-cpu` (Facebook AI Similarity Search) para armazenar e buscar vetores de similaridade de forma eficiente localmente.
    *   **Embeddings:** Utiliza `sentence-transformers` (modelo `all-MiniLM-L6-v2`) para converter textos em vetores numéricos.
    *   **LLM (Geração de Texto):** Integração com a **DeepSeek API** (compatível com OpenAI) para gerar as respostas finais baseadas no contexto recuperado.
*   **Frontend:**
    *   Página HTML simples servida estaticamente em [static/index.html](cci:7://file:///home/gustavo/statistica_gado/mvp-seguros-rag/static/index.html:0:0-0:0).

### 3. Estrutura de Arquivos
*   **[main.py](cci:7://file:///home/gustavo/statistica_gado/mvp-seguros-rag/main.py:0:0-0:0)**: O coração da aplicação. Define as rotas (`/upload`, `/ask`, `/health`), configura o CORS e inicializa os serviços.
*   **[run.py](cci:7://file:///home/gustavo/statistica_gado/mvp-seguros-rag/run.py:0:0-0:0)**: Script utilitário para verificar dependências, configurar o ambiente ([.env](cci:7://file:///home/gustavo/statistica_gado/mvp-seguros-rag/.env:0:0-0:0)), criar diretórios necessários e iniciar o servidor.
*   **[vector_store_faiss.py](cci:7://file:///home/gustavo/statistica_gado/mvp-seguros-rag/vector_store_faiss.py:0:0-0:0)**: Gerencia o banco de dados vetorial. Responsável por:
    *   Dividir o texto em pedaços (chunks).
    *   Gerar embeddings.
    *   Adicionar documentos ao índice FAISS.
    *   Realizar buscas por similaridade.
    *   Persistir os dados em disco (pasta `faiss_db`).
*   **[llm_service.py](cci:7://file:///home/gustavo/statistica_gado/mvp-seguros-rag/llm_service.py:0:0-0:0)**: Gerencia a comunicação com a API da DeepSeek. Constrói o prompt do sistema instruindo a IA a agir como um especialista em seguros Bradesco.
*   **[requirements.txt](cci:7://file:///home/gustavo/statistica_gado/mvp-seguros-rag/requirements.txt:0:0-0:0)**: Lista as dependências do projeto.
*   **`static/`**: Diretório para arquivos do frontend.
*   **`temp_uploads/`**: Diretório temporário para processamento de uploads.

### 4. Fluxo de Funcionamento
1.  **Upload:** O usuário envia um PDF. O sistema extrai o texto, divide em fragmentos, converte em vetores e salva no índice FAISS.
2.  **Pergunta:** O usuário envia uma pergunta.
3.  **Busca (Retrieval):** O sistema converte a pergunta em vetor e busca os trechos mais similares no FAISS.
4.  **Geração (Generation):** Os trechos encontrados são enviados junto com a pergunta para a API da DeepSeek, que formula a resposta final.

### Próximos Passos Sugeridos
Se você quiser rodar ou modificar o projeto:
1.  Certifique-se de ter um arquivo [.env](cci:7://file:///home/gustavo/statistica_gado/mvp-seguros-rag/.env:0:0-0:0) com a `DEEPSEEK_API_KEY` válida.
2.  Use `python run.py` para iniciar (ele verifica tudo para você).
3.  Acesse `http://localhost:8000` para testar.

Deseja que eu execute alguma tarefa específica, como rodar o projeto, criar testes ou modificar alguma funcionalidade?