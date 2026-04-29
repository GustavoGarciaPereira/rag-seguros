"""Fixtures reutilizáveis para a suíte de testes do Help Corretor.

Registra o marker ``slow`` para testes que chamam LLM real (DeepSeek).
"""
from __future__ import annotations

import os
import tempfile
from typing import Generator, List
from unittest.mock import MagicMock

import pytest

from app.core.config import Settings
from app.infrastructure.repositories.sqlite_chat_history import SQLiteChatHistory


# ---------------------------------------------------------------------------
# Marker de testes lentos (chamam LLM real)
# ---------------------------------------------------------------------------


def pytest_configure(config: pytest.Config) -> None:
    """Registra o marker ``slow`` para testes que dependem de API externa."""
    config.addinivalue_line(
        "markers",
        "slow: testes que chamam a API DeepSeek (pular com `-m 'not slow'`)",
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_dir() -> Generator[str, None, None]:
    """Diretório temporário para bancos SQLite de teste.

    Yields o caminho do diretório e o remove ao final.
    """
    tmpdir = tempfile.mkdtemp(prefix="help_corretor_test_")
    yield tmpdir
    import shutil

    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def chat_history() -> SQLiteChatHistory:
    """Instância de :class:`SQLiteChatHistory` em banco ``:memory:``.

    Útil para testes unitários que não precisam de persistência real.
    O banco é efêmero e isolado entre testes.
    """
    return SQLiteChatHistory(db_path=":memory:")


@pytest.fixture
def settings() -> Settings:
    """Settings com chave dummy — para testes que não chamam API real.

    Força ``DEEPSEEK_API_KEY`` e ``ADMIN_API_KEY`` com placeholders
    para evitar falhas por variável de ambiente ausente.
    """
    os.environ.setdefault("DEEPSEEK_API_KEY", "sk-dummy-test-key")
    os.environ.setdefault("ADMIN_API_KEY", "dummy-admin-key")
    return Settings()


# ---------------------------------------------------------------------------
# Mock fixtures para testes unitários (sem I/O real)
# ---------------------------------------------------------------------------

_MOCK_CHUNKS: List[MagicMock] = [
    MagicMock(
        text="Trecho sobre cobertura de vidros e para-brisas.",
        source="manual.pdf",
        page=1,
        relevance_score=0.9,
    ),
    MagicMock(
        text="Trecho sobre franquia obrigatória em sinistros.",
        source="manual.pdf",
        page=2,
        relevance_score=0.85,
    ),
    MagicMock(
        text="Trecho sobre carro reserva e diárias.",
        source="manual.pdf",
        page=3,
        relevance_score=0.8,
    ),
]


@pytest.fixture
def mock_vector_repo():
    """VectorRepository mockado que retorna chunks fictícios."""
    repo = MagicMock()
    repo.search.return_value = _MOCK_CHUNKS
    return repo


@pytest.fixture
def mock_reranker():
    """Reranker que repassa os resultados sem alterar ordem."""
    reranker = MagicMock()

    def fake_rerank(query, results):
        return list(results)

    reranker.rerank.side_effect = fake_rerank
    return reranker


@pytest.fixture
def mock_llm():
    """LLMGateway mockado com respostas controladas."""
    llm = MagicMock()
    llm.generate.return_value = "Resposta mockada do LLM com **Markdown**."
    llm.generate_stream.return_value = iter(
        ["Resposta ", "mockada ", "em ", "stream."]
    )
    return llm


@pytest.fixture
def mock_chat_history():
    """ChatHistory mockado para testes de memória."""
    history = MagicMock()
    history.get_recent_messages.return_value = []
    return history


@pytest.fixture
def mock_openai_client():
    """Mock do cliente OpenAI para testar DeepSeekGateway."""
    client = MagicMock()
    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_message = MagicMock()
    mock_message.content = "Resposta de teste do DeepSeek."
    mock_choice.message = mock_message
    mock_response.choices = [mock_choice]
    client.chat.completions.create.return_value = mock_response
    return client
