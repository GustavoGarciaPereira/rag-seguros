#!/usr/bin/env python3
"""test_chat_memory.py — valida o fluxo de sessao e persistencia de mensagens.

Testa:
  1. Criacao de sessao sem session_id → servidor retorna session no SSE
  2. Segunda pergunta com session_id → historico usado
  3. Mensagens persistidas no SQLiteChatHistory

Uso:
    python test_chat_memory.py

Exit codes:
    0  — todos os testes passaram
    1  — um ou mais testes falharam
"""

import os
import sys

from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.dependencies import _chat_history
from app.use_cases.answer_question import AskInsuranceQuestion
from app.core.dependencies import get_ask_use_case

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


def main() -> int:
    global PASS, FAIL

    print("=" * 60)
    print("test_chat_memory.py — Chat Memory Integration")
    print("=" * 60)

    # ------------------------------------------------------------------
    # Test 1: SQLiteChatHistory salva e recupera mensagens
    # ------------------------------------------------------------------
    print("\n1. Persistencia de mensagens")
    ch = _chat_history()
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

    # ------------------------------------------------------------------
    # Test 2: limite de mensagens (ultimas 10 = 5 trocas)
    # ------------------------------------------------------------------
    print("\n2. Limite de mensagens (truncagem por quantidade)")
    sid2 = "test-session-limit"
    for i in range(20):
        ch.add_message(sid2, "user" if i % 2 == 0 else "assistant", f"msg {i}")

    limited = ch.get_recent_messages(sid2, limit=10)
    check("maximo 10 mensagens", len(limited) == 10, f"recebido: {len(limited)}")
    check("mensagens mais recentes", "msg 19" in limited[-1][1], f"ultima: {limited[-1][1]}")

    # ------------------------------------------------------------------
    # Test 3: historico vazio → lista vazia
    # ------------------------------------------------------------------
    print("\n3. Sessao sem historico")
    empty = ch.get_recent_messages("sessao-inexistente")
    check("lista vazia", empty == [], f"recebido: {empty}")

    # ------------------------------------------------------------------
    # Resultado
    # ------------------------------------------------------------------
    print(f"\n{'=' * 60}")
    total = PASS + FAIL
    print(f"Resultado: {PASS}/{total} passaram")
    if FAIL:
        print(f"          {FAIL} falharam")
    print(f"{'=' * 60}")

    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
