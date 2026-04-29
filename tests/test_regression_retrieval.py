#!/usr/bin/env python3
"""test_regression_retrieval.py — valida qualidade de recuperação de chunks (sem servidor HTTP).

Executa o pipeline RAG completo via get_ask_use_case() e verifica se os chunks
retornados para a query de "carro reserva" contêm os termos esperados.

Uso:
    python tests/test_regression_retrieval.py
    python -m pytest tests/test_regression_retrieval.py -v

Exit codes (standalone):
    0  — >= 5 chunks relevantes retornados (teste passou)
    1  — < 5 chunks relevantes (qualidade de recuperação abaixo do esperado)
"""

import os
import sys

# Garante que a raiz do projeto esteja no sys.path para execução standalone
_proj_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _proj_root not in sys.path:
    sys.path.insert(0, _proj_root)

from dotenv import load_dotenv
load_dotenv()

# ---------------------------------------------------------------------------
# Skip condicional: se o índice FAISS não existir, o teste não pode rodar
# ---------------------------------------------------------------------------

_FAISS_INDEX = os.path.join(_proj_root, "faiss_db", "faiss_index.bin")
_NO_FAISS = not os.path.exists(_FAISS_INDEX)

import pytest

# Em modo pytest: skip silencioso se não há índice
if _NO_FAISS and "pytest" in sys.modules:
    pytest.skip("Índice FAISS não encontrado — execute 'python reindex.py' primeiro", allow_module_level=True)

# ---------------------------------------------------------------------------
# Configuração do teste
# ---------------------------------------------------------------------------

QUESTION = (
    "Quais são as opções de carro reserva (Básico, Plus, Premium) "
    "e como funcionam as diárias?"
)
FILTER = {"ramo": "Automovel"}
TOP_K = 15
RELEVANCE_TERMS = ["básico", "plus", "premium", "diária", "diárias", "carro reserva"]
MIN_RELEVANT = 5

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_relevant(text: str) -> bool:
    lower = text.lower()
    return any(term in lower for term in RELEVANCE_TERMS)


def _snippet(text: str, n: int = 80) -> str:
    text = text.replace("\n", " ").strip()
    return text[:n] + "…" if len(text) > n else text

# ---------------------------------------------------------------------------
# Pytest entry point
# ---------------------------------------------------------------------------

@pytest.mark.timeout(60)
def test_retrieval_quality():
    """Verifica se ao menos MIN_RELEVANT chunks relevantes são retornados.

    Usa apenas FAISS + reranker — sem chamar o LLM (DeepSeek).
    """
    if _NO_FAISS:
        pytest.skip("Índice FAISS não encontrado")

    from app.infrastructure.repositories.faiss_repository import FAISSVectorRepository
    from app.infrastructure.rerankers.keyword_reranker import KeywordOverlapReranker

    vector_repo = FAISSVectorRepository()
    reranker = KeywordOverlapReranker()

    # Busca + reranking (sem LLM — mesmo pipeline do AskInsuranceQuestion)
    candidates = vector_repo.search(QUESTION, n_results=TOP_K * 4, filter_dict=FILTER)
    results = reranker.rerank(QUESTION, candidates)[:TOP_K]

    assert results, "Nenhum chunk retornado. Verifique se o índice está populado."

    n_relevant = sum(1 for r in results if _is_relevant(r.text))
    assert n_relevant >= MIN_RELEVANT, (
        f"Apenas {n_relevant}/{len(results)} chunks relevantes "
        f"(mínimo esperado: {MIN_RELEVANT})"
    )

# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 70)
    print("  REGRESSION TEST — Recuperação de chunks: Carro Reserva / Automóvel")
    print("=" * 70)
    print(f"\n  Query   : {QUESTION}")
    print(f"  Filtro  : {FILTER}")
    print(f"  top_k   : {TOP_K}")
    print(f"  Termos  : {RELEVANCE_TERMS}")
    print()

    if _NO_FAISS:
        print("  ERRO: Índice FAISS não encontrado.")
        print("  Execute 'python reindex.py' primeiro.")
        sys.exit(1)

    # Busca + reranking direto (sem LLM)
    from app.infrastructure.repositories.faiss_repository import FAISSVectorRepository
    from app.infrastructure.rerankers.keyword_reranker import KeywordOverlapReranker

    vector_repo = FAISSVectorRepository()
    reranker = KeywordOverlapReranker()
    print("  Executando busca FAISS + reranking (sem LLM)...\n")

    candidates = vector_repo.search(QUESTION, n_results=TOP_K * 4, filter_dict=FILTER)
    results = reranker.rerank(QUESTION, candidates)[:TOP_K]

    if not results:
        print("  ERRO: Nenhum chunk retornado. Verifique se o índice está populado.")
        sys.exit(1)

    # ── Tabela de resultados ──────────────────────────────────────────────
    print(f"  {'Rank':<5} {'Score':>6}  {'Fonte':<28} {'Pág':>4}  {'Texto':}")
    print(f"  {'-'*5} {'-'*6}  {'-'*28} {'-'*4}  {'-'*50}")

    n_relevant = 0
    for rank, r in enumerate(results, 1):
        relevant = _is_relevant(r.text)
        if relevant:
            n_relevant += 1
        mark = "✅" if relevant else "  "
        source = r.source[:26] + "…" if len(r.source) > 27 else r.source
        snippet = _snippet(r.text)
        print(f"  {mark} {rank:<3} {r.relevance_score:>6.3f}  {source:<28} {r.page:>4}  {snippet}")

    # ── Resultado ─────────────────────────────────────────────────────────
    print()
    print(f"  {n_relevant}/{len(results)} chunks relevantes retornados")

    passed = n_relevant >= MIN_RELEVANT
    status = "PASSOU ✅" if passed else "FALHOU ❌"
    threshold = f"(mínimo esperado: {MIN_RELEVANT})"
    print(f"  Resultado: {status} {threshold}")
    print("=" * 70)

    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
