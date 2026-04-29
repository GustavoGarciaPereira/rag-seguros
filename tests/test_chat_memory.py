#!/usr/bin/env python3
"""test_chat_memory.py — valida o fluxo de sessao e persistencia de mensagens.

Testa:
  1. SQLiteChatHistory salva e recupera mensagens corretamente
  2. Limite de mensagens funciona (ultimas N)
  3. Sessao sem historico retorna lista vazia

Uso:
    python tests/test_chat_memory.py
    python -m pytest tests/test_chat_memory.py -v
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
# Skip condicional: se o índice FAISS não existir, os testes que dependem
# de get_ask_use_case() não podem rodar.
# ---------------------------------------------------------------------------

_FAISS_INDEX = os.path.join(_proj_root, "faiss_db", "faiss_index.bin")
_NO_FAISS = not os.path.exists(_FAISS_INDEX)

import pytest

# Se for execução via pytest e não há índice FAISS, skip tudo
if _NO_FAISS and "pytest" in sys.modules:
    pytest.skip("FAISS index not found — run 'python reindex.py' first", allow_module_level=True)

from app.core.dependencies import _chat_history

PASS = 0
FAIL = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}  — {detail}")


# ---------------------------------------------------------------------------
# Test fixtures / setup
# ---------------------------------------------------------------------------

@pytest.fixture
def ch():
    """Retorna o singleton SQLiteChatHistory."""
    return _chat_history()


# ---------------------------------------------------------------------------
# Test 1: Persistência de mensagens
# ---------------------------------------------------------------------------

def test_message_persistence(ch) -> None:
    """SQLiteChatHistory salva e recupera mensagens corretamente."""
    sid = "test-session-integration"

    ch.add_message(sid, "user", "Qual o valor da franquia?")
    ch.add_message(sid, "assistant", "A franquia e de R$ 1.000,00.")
    ch.add_message(sid, "user", "E para veiculos 0km?")
    ch.add_message(sid, "assistant", "Para veiculos 0km a franquia e de R$ 2.500,00.")

    recent = ch.get_recent_messages(sid, limit=4)
    assert len(recent) == 4, f"Esperado 4, recebido {len(recent)}"
    assert recent[0][0] == "user", f"role: {recent[0][0]}"
    assert recent[-1][0] == "assistant", f"role: {recent[-1][0]}"
    assert "franquia" in recent[1][1].lower()


# ---------------------------------------------------------------------------
# Test 2: Limite de mensagens
# ---------------------------------------------------------------------------

def test_message_limit(ch) -> None:
    """Limite de mensagens retorna apenas as ultimas N."""
    sid = "test-session-limit"
    for i in range(20):
        ch.add_message(sid, "user" if i % 2 == 0 else "assistant", f"msg {i}")

    limited = ch.get_recent_messages(sid, limit=10)
    assert len(limited) == 10, f"Esperado 10, recebido {len(limited)}"
    assert "msg 19" in limited[-1][1], f"ultima: {limited[-1][1]}"


# ---------------------------------------------------------------------------
# Test 3: Sessão sem histórico
# ---------------------------------------------------------------------------

def test_empty_session(ch) -> None:
    """Sessao inexistente retorna lista vazia."""
    empty = ch.get_recent_messages("sessao-inexistente")
    assert empty == [], f"Esperado lista vazia, recebido {empty}"


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------

def main() -> int:
    global PASS, FAIL
    PASS = 0
    FAIL = 0

    print("=" * 60)
    print("test_chat_memory.py — Chat Memory Integration")
    print("=" * 60)

    if _NO_FAISS:
        print("\n  ⚠️  FAISS index não encontrado. Pulando testes de integração.")
        print("  Execute 'python reindex.py' primeiro.\n")
        print(f"{'=' * 60}")
        return 0

    ch = _chat_history()

    # Test 1
    print("\n1. Persistencia de mensagens")
    sid = "test-session-integration"
    ch.add_message(sid, "user", "Qual o valor da franquia?")
    ch.add_message(sid, "assistant", "A franquia e de R$ 1.000,00.")
    ch.add_message(sid, "user", "E para veiculos 0km?")
    ch.add_message(sid, "assistant", "Para veiculos 0km a franquia e de R$ 2.500,00.")
    recent = ch.get_recent_messages(sid, limit=4)
    check("4 mensagens recuperadas", len(recent) == 4, f"recebido: {len(recent)}")
    check("primeira e do usuario", recent[0][0] == "user", f"role: {recent[0][0]}")
    check("ultima e do assistant", recent[-1][0] == "assistant", f"role: {recent[-1][0]}")
    check("conteudo preservado", "franquia" in recent[1][1].lower())

    # Test 2
    print("\n2. Limite de mensagens (truncagem por quantidade)")
    sid2 = "test-session-limit"
    for i in range(20):
        ch.add_message(sid2, "user" if i % 2 == 0 else "assistant", f"msg {i}")
    limited = ch.get_recent_messages(sid2, limit=10)
    check("maximo 10 mensagens", len(limited) == 10, f"recebido: {len(limited)}")
    check("mensagens mais recentes", "msg 19" in limited[-1][1], f"ultima: {limited[-1][1]}")

    # Test 3
    print("\n3. Sessao sem historico")
    empty = ch.get_recent_messages("sessao-inexistente")
    check("lista vazia", empty == [], f"recebido: {empty}")

    # Resultado
    print(f"\n{'=' * 60}")
    total = PASS + FAIL
    print(f"Resultado: {PASS}/{total} passaram")
    if FAIL:
        print(f"          {FAIL} falharam")
    print(f"{'=' * 60}")

    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
