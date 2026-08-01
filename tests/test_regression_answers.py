#!/usr/bin/env python3
"""test_regression_answers.py — valida qualidade estrutural das respostas geradas.

Verifica que as respostas a perguntas de cobertura contêm as seções obrigatórias
e atingem o tamanho mínimo esperado.

Uso:
    python tests/test_regression_answers.py          # standalone
    python -m pytest tests/test_regression_answers.py -v  # via pytest
    python -m pytest tests/ -m "not slow"                 # pula este teste

Exit codes (standalone):
    0  — todos os testes passaram
    1  — um ou mais testes falharam
"""

import os
import sys
from typing import Any, Dict, List

# Garante que a raiz do projeto esteja no sys.path para execução standalone
_proj_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _proj_root not in sys.path:
    sys.path.insert(0, _proj_root)

from dotenv import load_dotenv
load_dotenv()

# ---------------------------------------------------------------------------
# Verificação de conectividade DeepSeek (executada UMA vez no import)
# ---------------------------------------------------------------------------

import pytest as _pytest  # noqa: E402

def _can_reach_deepseek() -> bool:
    """Verifica conectividade com a API DeepSeek em duas etapas:

    1. TCP socket para api.deepseek.com:443 (3 s timeout) — barato e rápido.
    2. Chamada mínima à API (5 s timeout) se a chave existir.
    Se qualquer etapa falhar, o módulo é pulado via pytestmark.
    """
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key or api_key == "sua_chave_aqui":
        return False

    # Etapa 1: conectividade TCP (sem gastar créditos)
    try:
        import socket
        sock = socket.create_connection(("api.deepseek.com", 443), timeout=3)
        sock.close()
    except Exception:
        return False

    # Etapa 2: chamada mínima à API com timeout curto
    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com",
            timeout=5.0,
            max_retries=0,
        )
        client.chat.completions.create(
            model="deepseek-v4-pro",
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1,
        )
        return True
    except Exception:
        return False

_CAN_REACH_DEEPSEEK = _can_reach_deepseek()

pytestmark = _pytest.mark.skipif(
    not _CAN_REACH_DEEPSEEK,
    reason="API DeepSeek nao disponivel (sem chave ou sem conectividade). Execute localmente.",
)

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
    {
        "question": "Como é calculada a indenização por perda total no seguro de automóvel?",
        "filter": {},
        "required_sections": [],
        "min_chars": 300,
        "required_terms": ["Bradesco", "Allianz", "180 dias"],
    },
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _check_sections(answer: str, required: List[str]) -> Dict[str, bool]:
    lower = answer.lower()
    return {section: section in lower for section in required}


def _run_test(query_config: Dict[str, Any]) -> bool:
    """Executa uma query e valida a resposta.  Retorna True se passou."""
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
        # NÃO é pass: se a API falhar durante o teste, a validação não foi
        # executada — o teste deve falhar (falso verde é pior que vermelho).
        print(f"  ❌ Falha ao executar a query (API indisponível durante o teste): {e}")
        print("  ⏭️ Validação não executada — rode localmente com a API disponível.")
        return False

    if not answer:
        print("  ERRO: Resposta vazia retornada.")
        return False

    passed = True

    # 1. Seções obrigatórias
    sections = _check_sections(answer, query_config["required_sections"])
    if sections:
        print("\n  Seções obrigatórias:")
        for section, found in sections.items():
            mark = "✅" if found else "❌"
            print(f"    {mark} {section}")
            if not found:
                passed = False
    else:
        print("\n  📋 Seções obrigatórias: (nenhuma especificada)")

    # 1b. Termos obrigatórios
    required_terms = query_config.get("required_terms", [])
    if required_terms:
        print("\n  🔍 Termos obrigatórios:")
        for term in required_terms:
            found = term.lower() in answer.lower()
            mark = "✅" if found else "❌"
            print(f"    {mark} {term}")
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

    # Salva saída para inspeção manual (na raiz do projeto)
    slug = query_config["question"].replace(" ", "_")[:40]
    out_file = os.path.join(_proj_root, f"test_output_{slug}.txt")
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
# Pytest entry point (marcado como lento — chama API DeepSeek real)
# ---------------------------------------------------------------------------

import pytest  # noqa: E402 (import após helpers para ficar claro)


@pytest.mark.slow
def test_answer_quality() -> None:
    """Valida qualidade estrutural das respostas geradas pelo LLM.

    Este teste faz chamadas reais à API DeepSeek e é marcado como ``slow``.
    Pule com ``pytest -m 'not slow'``.
    """
    for query_config in TEST_QUERIES:
        passed = _run_test(query_config)
        assert passed, f"Falhou na query: {query_config['question'][:60]}"


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 70)
    print("  REGRESSION TEST — Qualidade das Respostas (Estrutural)")
    print("=" * 70)

    if not _CAN_REACH_DEEPSEEK:
        # Skip explícito (não é pass silencioso): a mensagem aparece nos logs do CI
        print("\n  ⏭️  SKIP: API DeepSeek indisponível (sem chave ou sem conectividade).")
        print("      Nenhuma validação foi executada. Rode localmente com a API disponível.")
        sys.exit(0)

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
