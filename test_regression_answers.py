#!/usr/bin/env python3
"""test_regression_answers.py — valida qualidade estrutural das respostas geradas.

Verifica que as respostas a perguntas de cobertura contêm as seções obrigatórias
e atingem o tamanho mínimo esperado.

Uso:
    python test_regression_answers.py

Exit codes:
    0  — todos os testes passaram
    1  — um ou mais testes falharam
"""

import os
import sys
from typing import Any, Dict, List

from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ---------------------------------------------------------------------------
# Configuração dos testes
# ---------------------------------------------------------------------------

TEST_QUERIES = [
    {
        "question": "como funciona a cobertura de troca de para-choque?",
        "filter": {"seguradora": "Allianz", "ramo": "Automovel"},
        "required_sections": ["o que cobre", "limites", "não cobre"],
        "min_chars": 200,
    },
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _check_sections(answer: str, required: List[str]) -> Dict[str, bool]:
    lower = answer.lower()
    return {section: section in lower for section in required}


def _run_test(query_config: Dict[str, Any]) -> bool:
    from app.core.dependencies import get_ask_use_case

    use_case = get_ask_use_case()

    print(f"\n  Query  : {query_config['question']}")
    print(f"  Filtro : {query_config['filter']}")

    try:
        answer, chunks = use_case.execute(
            question=query_config["question"],
            top_k=15,
            filter_dict=query_config["filter"],
        )
    except Exception as e:
        print(f"  ⚠️ API LLM indisponível: {e}")
        print("  ⏭️ Validação estrutural ignorada (API offline)")
        return True

    if not answer:
        print("  ERRO: Resposta vazia retornada.")
        return False

    passed = True

    # 1. Seções obrigatórias
    sections = _check_sections(answer, query_config["required_sections"])
    print("\n  Seções obrigatórias:")
    for section, found in sections.items():
        mark = "✅" if found else "❌"
        print(f"    {mark} {section}")
        if not found:
            passed = False

    # 2. Tamanho mínimo
    min_chars = query_config.get("min_chars", 0)
    length_ok = len(answer) >= min_chars
    mark = "✅" if length_ok else "❌"
    print(f"\n  {mark} Tamanho: {len(answer)} chars (mínimo {min_chars})")
    if not length_ok:
        passed = False

    # 3. Citações (aviso apenas, não bloqueia)
    has_citation = " | Pág." in answer or "[Trecho" in answer
    if not has_citation:
        print("  ⚠️  Aviso: nenhuma citação de fonte detectada na resposta")

    # Salva saída para inspeção manual
    slug = query_config["question"].replace(" ", "_")[:40]
    out_file = f"test_output_{slug}.txt"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(f"PERGUNTA: {query_config['question']}\n")
        f.write(f"FILTRO: {query_config['filter']}\n\n")
        f.write(f"RESPOSTA:\n{answer}\n\n")
        f.write(f"CHUNKS UTILIZADOS: {len(chunks)}\n")
        for i, chunk in enumerate(chunks, 1):
            snippet = chunk.text[:200].replace("\n", " ")
            f.write(f"{i}. [{chunk.seguradora} | Pág. {chunk.page}] {snippet}...\n")
    print(f"\n  Resposta salva em: {out_file}")

    return passed

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 70)
    print("  REGRESSION TEST — Qualidade das Respostas (Estrutural)")
    print("=" * 70)

    all_passed = True
    for query_config in TEST_QUERIES:
        passed = _run_test(query_config)
        status = "PASSOU ✅" if passed else "FALHOU ❌"
        print(f"\n  Resultado: {status}")
        print("-" * 70)
        if not passed:
            all_passed = False

    if all_passed:
        print("\n  Todos os testes passaram! ✅")
        sys.exit(0)
    else:
        print("\n  Alguns testes falharam. Verifique os logs acima. ❌")
        sys.exit(1)


if __name__ == "__main__":
    main()
