
"""Testes unitários para DeepSeekGateway.

Usa mock do cliente OpenAI (openai.OpenAI) para testar:
- generate() com e sem retry
- generate_stream() com tokens
- Formatação de contexto e prompt do sistema
"""
import pytest
from unittest.mock import MagicMock, patch

from app.domain.entities.document import SearchResult


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _make_chunks():
    return [
        SearchResult(
            text="Trecho sobre cobertura de vidros.",
            source="manual_bradesco.pdf",
            page=1,
            seguradora="Bradesco",
            ramo="Automovel",
            relevance_score=0.9,
        ),
        SearchResult(
            text="Trecho sobre franquia obrigatória.",
            source="manual_allianz.pdf",
            page=2,
            seguradora="Allianz",
            ramo="Automovel",
            relevance_score=0.85,
        ),
    ]


# ------------------------------------------------------------------
# Test: generate()
# ------------------------------------------------------------------

def test_generate_returns_response(mock_openai_client):
    """generate() retorna a string de resposta do mock OpenAI."""
    from app.infrastructure.gateways.deepseek_gateway import DeepSeekGateway

    gateway = DeepSeekGateway()
    gateway._client = mock_openai_client
    gateway._model = "test-model"

    answer = gateway.generate("Pergunta de teste?", _make_chunks())

    assert answer == "Resposta de teste do DeepSeek."
    mock_openai_client.chat.completions.create.assert_called_once()
    call_kwargs = mock_openai_client.chat.completions.create.call_args[1]
    assert call_kwargs["model"] == "test-model"
    assert not call_kwargs["stream"]
    assert call_kwargs["temperature"] == 0.3
    assert call_kwargs["max_tokens"] == 4000


def test_generate_retry_on_failure():
    """generate() tenta novamente após falha (até max_retries vezes)."""
    from app.infrastructure.gateways.deepseek_gateway import DeepSeekGateway

    client = MagicMock()
    success = MagicMock()
    success.choices = [MagicMock(message=MagicMock(content="Sucesso apos retry"))]
    client.chat.completions.create.side_effect = [
        RuntimeError("Rate limit"),
        RuntimeError("Rate limit"),
        success,
    ]

    gateway = DeepSeekGateway(max_retries=3)
    gateway._client = client

    answer = gateway.generate("teste", _make_chunks())
    assert answer == "Sucesso apos retry"
    assert client.chat.completions.create.call_count == 3


def test_generate_all_retries_fail():
    """Se todas as tentativas falham, retorna mensagem de fallback."""
    from app.infrastructure.gateways.deepseek_gateway import DeepSeekGateway

    client = MagicMock()
    client.chat.completions.create.side_effect = RuntimeError("Falha persistente")

    gateway = DeepSeekGateway(max_retries=2)
    gateway._client = client

    answer = gateway.generate("teste", _make_chunks())
    assert "Desculpe" in answer
    assert client.chat.completions.create.call_count == 2


# ------------------------------------------------------------------
# Test: generate_stream()
# ------------------------------------------------------------------

def test_generate_stream_yields_tokens():
    """generate_stream() cede tokens do stream mockado."""
    from app.infrastructure.gateways.deepseek_gateway import DeepSeekGateway

    client = MagicMock()
    mock_chunk1 = MagicMock()
    mock_chunk1.choices = [MagicMock(delta=MagicMock(content="token1"))]
    mock_chunk2 = MagicMock()
    mock_chunk2.choices = [MagicMock(delta=MagicMock(content="token2"))]
    mock_chunk3 = MagicMock()
    mock_chunk3.choices = [MagicMock(delta=MagicMock(content="token3"))]
    client.chat.completions.create.return_value = [mock_chunk1, mock_chunk2, mock_chunk3]

    gateway = DeepSeekGateway()
    gateway._client = client

    tokens = list(gateway.generate_stream("teste", _make_chunks()))
    assert tokens == ["token1", "token2", "token3"]
    assert client.chat.completions.create.call_count == 1
    assert client.chat.completions.create.call_args[1]["stream"] is True


# ------------------------------------------------------------------
# Test: _format_context
# ------------------------------------------------------------------

def test_format_context_output():
    """_format_context() retorna string com [Trecho N | Fonte: ... | Pág. N]."""
    from app.infrastructure.gateways.deepseek_gateway import DeepSeekGateway

    chunks = _make_chunks()
    formatted = DeepSeekGateway._format_context(chunks)

    assert "[Trecho 1 | Fonte: Bradesco" in formatted
    assert "| Pág. 1]" in formatted
    assert "[Trecho 2 | Fonte: Allianz" in formatted
    assert "| Pág. 2]" in formatted
    assert "vidros" in formatted


# ------------------------------------------------------------------
# Test: system prompt
# ------------------------------------------------------------------

def test_system_prompt_contains_required_sections():
    """O _SYSTEM_PROMPT contém as 4 seções obrigatórias do auditor."""
    from app.infrastructure.gateways.deepseek_gateway import _SYSTEM_PROMPT

    assert "VEREDITO DIRETO" in _SYSTEM_PROMPT
    assert "DETALHES TÉCNICOS" in _SYSTEM_PROMPT
    assert 'LETRA MIÚDA' in _SYSTEM_PROMPT
    assert "PROVA DOCUMENTAL" in _SYSTEM_PROMPT
    assert "n_chunks" in _SYSTEM_PROMPT  # placeholder
