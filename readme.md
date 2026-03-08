# 🛡️ Help Corretor - Auditor IA para Seguros

**Help Corretor** é uma plataforma de inteligência artificial baseada em **RAG (Retrieval-Augmented Generation)** projetada para centralizar o conhecimento técnico de diversas seguradoras do mercado em uma interface única, ágil e auditável.

A ferramenta permite que colaboradores de corretoras consultem coberturas, limites e cláusulas complexas de manuais (PDFs) com precisão cirúrgica, eliminando a necessidade de navegar em múltiplos portais e reduzindo drasticamente o tempo de resposta ao cliente.

## 🚀 Diferenciais "Antigravity"

Diferente de assistentes genéricos, o Help Corretor foi construído sob quatro pilares de confiança:

1. **Multi-Seguradora Real:** Suporte a múltiplos manuais com filtros de metadados para evitar o cruzamento de informações entre concorrentes.
2. **Grounding & Citações:** Cada resposta da IA é acompanhada de evidências no formato `[Seguradora | Pág. X]`.
3. **Recuperação Profunda (Top-K=10):** Calibrado para localizar "letras miúdas" em tabelas de assistência técnica e anexos de condições especiais.
4. **Resiliência de Metadados:** Sistema de *fallback* que utiliza o nome do arquivo para citações caso os metadados explícitos estejam ausentes.

---

## 🛠️ Stack Tecnológica

| Tecnologia | Função |
| --- | --- |
| **Python 3.10+** | Linguagem base do ecossistema. |
| **FastAPI** | Framework backend de alta performance e baixa latência. |
| **FAISS (CPU)** | Banco de dados vetorial local para busca de similaridade eficiente. |
| **DeepSeek API** | LLM de ponta (OpenAI compatible) para raciocínio lógico e auditoria. |
| **Sentence-Transformers** | Modelo `all-MiniLM-L6-v2` para geração de embeddings leves. |

---

## 🏗️ Arquitetura do Sistema

O fluxo de dados segue uma esteira de processamento otimizada:

1. **Ingestão:** Upload de PDFs via `/admin/upload` com validação de seguradoras homologadas.
2. **Fragmentação:** Divisão do texto em *chunks* de 1200 caracteres com 200 de sobreposição (*overlap*).
3. **Vetorização:** Cada fragmento é convertido em vetor e indexado com metadados de página e seguradora.
4. **Consulta:** Busca filtrada por seguradora com recuperação dos 10 fragmentos mais relevantes.
5. **Auditoria:** A IA processa o contexto e gera uma resposta estruturada com referências diretas.

---

## ⚙️ Configuração e Instalação

### 1. Requisitos

* Python 3.10 ou superior.
* Uma chave de API da DeepSeek.

### 2. Instalação

```bash
# Clone o repositório
git clone https://github.com/GustavoGarciaPereira/mvp-seguros-rag.git

# Entre no diretório
cd mvp-seguros-rag

# Instale as dependências
pip install -r requirements.txt

```

### 3. Variáveis de Ambiente

Crie um arquivo `.env` na raiz do projeto:

```env
DEEPSEEK_API_KEY=sua_chave_aqui

```

### 4. Execução

```bash
python run.py

```

Acesse `http://localhost:8000` para começar. O chat será desbloqueado automaticamente se houver uma base de dados ativa.

---

## 📅 Roadmap de Evolução

* [x] Suporte Multi-Seguradora e Filtros.
* [x] Sistema de Citações e Grounding.
* [x] Lógica de Fallback de Metadados.
* [ ] Painel de Inventário (Lista de manuais ativos).
* [ ] Backup Automatizado do Índice FAISS para Cloud.
* [ ] Exportação de Relatório de Auditoria em PDF.

---

## 📄 Licença

Distribuído sob a licença MIT. Veja `LICENSE` para mais informações.

---

**Feito por Gustavo Garcia Pereira** — *Focado em transformar complexidade técnica em agilidade para o corretor.*
