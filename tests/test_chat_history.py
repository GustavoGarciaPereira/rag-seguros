"""Testes unitários para SQLiteChatHistory."""

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.infrastructure.repositories.sqlite_chat_history import SQLiteChatHistory


@pytest.fixture
def chat_history():
    """Cria um SQLiteChatHistory em um arquivo temporário."""
    fd, path = tempfile.mkstemp(suffix=".db", prefix="test_chat_")
    os.close(fd)
    ch = SQLiteChatHistory(db_path=path)
    yield ch
    os.unlink(path)


def test_add_and_retrieve_messages(chat_history):
    chat_history.add_message("sessao-1", "user", "Qual a franquia?")
    chat_history.add_message("sessao-1", "assistant", "A franquia é de R$ 500,00.")

    msgs = chat_history.get_recent_messages("sessao-1")
    assert len(msgs) == 2
    assert msgs[0] == ("user", "Qual a franquia?")
    assert msgs[1] == ("assistant", "A franquia é de R$ 500,00.")


def test_session_isolation(chat_history):
    chat_history.add_message("sessao-1", "user", "Pergunta A")
    chat_history.add_message("sessao-2", "user", "Pergunta B")

    msgs_1 = chat_history.get_recent_messages("sessao-1")
    msgs_2 = chat_history.get_recent_messages("sessao-2")
    assert len(msgs_1) == 1
    assert msgs_1[0][1] == "Pergunta A"
    assert len(msgs_2) == 1
    assert msgs_2[0][1] == "Pergunta B"


def test_limit_parameter(chat_history):
    for i in range(15):
        chat_history.add_message("sessao-3", "user", f"Pergunta {i}")
        chat_history.add_message("sessao-3", "assistant", f"Resposta {i}")

    msgs = chat_history.get_recent_messages("sessao-3", limit=6)
    assert len(msgs) == 6
    # As 6 últimas devem ser as mensagens mais recentes (3 últimas trocas)
    assert msgs[0][1] == "Pergunta 12"
    assert msgs[-1][1] == "Resposta 14"


def test_chronological_order(chat_history):
    chat_history.add_message("sessao-4", "user", "Primeira")
    chat_history.add_message("sessao-4", "assistant", "Segunda")
    chat_history.add_message("sessao-4", "user", "Terceira")

    msgs = chat_history.get_recent_messages("sessao-4")
    assert [m[1] for m in msgs] == ["Primeira", "Segunda", "Terceira"]


def test_invalid_role_raises(chat_history):
    with pytest.raises(ValueError, match="role inválido"):
        chat_history.add_message("sessao-5", "invalid", "conteudo")


def test_empty_session(chat_history):
    msgs = chat_history.get_recent_messages("sessao-inexistente")
    assert msgs == []
