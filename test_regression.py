#!/usr/bin/env python3
"""test_regression.py — valida qualidade de recuperação de chunks (sem servidor HTTP).

Executa o pipeline RAG completo via get_ask_use_case() e verifica se os chunks
retornados para a query de "carro reserva" contêm os termos esperados.

Uso:
    python test_regression.py

Exit codes:
    0  — >= 5 chunks relevantes retornados (teste passou)
    1  — < 5 chunks relevantes (qualidade de recuperação abaixo do esperado)
"""

import sys

from dotenv import load_dotenv
load_dotenv()

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
# Main
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

    # Importação deferida: evita carregar FAISS/modelo se houver erro de setup
    from app.core.dependencies import get_ask_use_case

    use_case = get_ask_use_case()
    print("  Executando pipeline RAG (inclui chamada ao LLM)...\n")

    _answer, results = use_case.execute(
        question=QUESTION,
        top_k=TOP_K,
        filter_dict=FILTER,
    )

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
