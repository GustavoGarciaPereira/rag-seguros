
"""Testes unitários para AskInsuranceQuestion (use case de RAG).

Usa mocks para VectorRepository, Reranker, LLMGateway e ChatHistory,
eliminando dependência de FAISS, DeepSeek e SQLite reais.
"""
from typing import List

import pytest

from app.domain.entities.document import SearchResult
from app.use_cases.answer_question import AskInsuranceQuestion


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _make_use_case(mock_vector_repo, mock_reranker, mock_llm, mock_chat_history=None):
    return AskInsuranceQuestion(
        vector_repo=mock_vector_repo,
        reranker=mock_reranker,
        llm=mock_llm,
        chat_history=mock_chat_history,
    )


# ------------------------------------------------------------------
# Test: execute() - caminho feliz
# ------------------------------------------------------------------

def test_execute_returns_tuple(mock_vector_repo, mock_reranker, mock_llm, mock_chat_history):
    """execute() retorna tupla (answer, results) e chama as 3 camadas."""
    uc = _make_use_case(mock_vector_repo, mock_reranker, mock_llm, mock_chat_history)

    answer, results = uc.execute(question="teste?", top_k=5, filter_dict=None, session_id="abc")

    assert answer == "Resposta mockada do LLM com **Markdown**."
    assert len(results) == 3
    # Camada 1: busca vetorial com fetch_k = top_k * 4
    mock_vector_repo.search.assert_called_once()
    call_args = mock_vector_repo.search.call_args
    assert call_args[1]["n_results"] == 20  # top_k=5 * 4
    # Camada 2: reranker
    mock_reranker.rerank.assert_called_once()
    # Camada 3: LLM
    mock_llm.generate.assert_called_once()
    # Camada 4: histórico
    assert mock_chat_history.add_message.call_count == 2


def test_execute_stream_yields_tokens(mock_vector_repo, mock_reranker, mock_llm, mock_chat_history):
    """execute_stream() gera tokens e persiste Q&A após consumo total."""
    uc = _make_use_case(mock_vector_repo, mock_reranker, mock_llm, mock_chat_history)

    results, gen = uc.execute_stream(question="teste?", top_k=5, filter_dict=None, session_id="abc")

    assert len(results) == 3
    tokens = list(gen)
    assert tokens == ["Resposta ", "mockada ", "em ", "stream."]
    # Histórico persistido após stream consumido
    assert mock_chat_history.add_message.call_count == 2


def test_history_injected_into_prompt(mock_vector_repo, mock_reranker, mock_llm, mock_chat_history):
    """Histórico da sessão é prefixado no prompt enviado ao LLM."""
    mock_chat_history.get_recent_messages.return_value = [
        ("user", "pergunta anterior?"),
        ("assistant", "resposta anterior."),
    ]
    uc = _make_use_case(mock_vector_repo, mock_reranker, mock_llm, mock_chat_history)

    uc.execute(question="pergunta atual?", top_k=5, filter_dict=None, session_id="abc")

    prompt_enviado = mock_llm.generate.call_args[0][0]
    assert "[Histórico recente da conversa]" in prompt_enviado
    assert "pergunta anterior?" in prompt_enviado
    assert "resposta anterior." in prompt_enviado


def test_no_session_id_skips_history(mock_vector_repo, mock_reranker, mock_llm, mock_chat_history):
    """Sem session_id, add_message NUNCA é chamado."""
    uc = _make_use_case(mock_vector_repo, mock_reranker, mock_llm, mock_chat_history)

    uc.execute(question="teste?", top_k=5, filter_dict=None, session_id=None)

    mock_chat_history.add_message.assert_not_called()


def test_execute_empty_context(mock_reranker, mock_llm, mock_chat_history):
    """Se FAISS retorna vazio, execute() retorna (None, []) sem chamar LLM."""
    from unittest.mock import MagicMock
    empty_repo = MagicMock()
    empty_repo.search.return_value = []

    uc = _make_use_case(empty_repo, mock_reranker, mock_llm, mock_chat_history)

    answer, results = uc.execute(question="nada?", top_k=5, filter_dict=None)

    assert answer is None
    assert results == []
    mock_llm.generate.assert_not_called()


def test_execute_stream_empty_context(mock_reranker, mock_llm, mock_chat_history):
    """Se FAISS retorna vazio, execute_stream() retorna ([], iter([]))."""
    from unittest.mock import MagicMock
    empty_repo = MagicMock()
    empty_repo.search.return_value = []

    uc = _make_use_case(empty_repo, mock_reranker, mock_llm, mock_chat_history)

    results, gen = uc.execute_stream(question="nada?", top_k=5, filter_dict=None)

    assert results == []
    assert list(gen) == []
    mock_llm.generate_stream.assert_not_called()
