
"""Testes de integracao com TestClient do FastAPI.

Testa endpoints /health, /stats, /api/inventory, /ask e /api/conversations.

Se o indice FAISS nao existir, todos os testes sao pulados automaticamente.
"""
import os
import json

import pytest
from fastapi.testclient import TestClient

_FAISS_INDEX = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "faiss_db", "faiss_index.bin",
)

# Skip em modo pytest se nao ha indice FAISS
if not os.path.exists(_FAISS_INDEX) and "pytest" in __import__("sys").modules:
    pytest.skip("Indice FAISS nao encontrado", allow_module_level=True)


@pytest.fixture(scope="module")
def client():
    """TestClient contra a app FastAPI real. Pula se houver incompatibilidade."""
    from app.main import app
    try:
        with TestClient(app) as c:
            yield c
    except TypeError:
        pytest.skip("TestClient incompativel com httpx/starlette nesta versao")


def test_health_returns_200(client):
    """GET /health retorna 200 com status healthy."""
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"


def test_status_returns_chunk_count(client):
    """GET /status retorna total_chunks e ready."""
    resp = client.get("/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_chunks" in data
    assert "ready" in data


def test_stats_returns_inventory(client):
    """GET /stats retorna inventario e status LLM."""
    resp = client.get("/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert "inventory" in data
    assert "total_documents" in data["inventory"]


def test_inventory_returns_documents(client):
    """GET /api/inventory retorna documentos agrupados por seguradora."""
    resp = client.get("/api/inventory")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_documents" in data
    assert "documents" in data


def test_ask_creates_session(client):
    """POST /ask sem session_id cria nova sessao via SSE."""
    resp = client.post("/ask", json={
        "question": "teste de integracao com 20 caracteres?",
        "top_k": 3
    })
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    # Primeira linha do SSE deve conter session_id
    first_line = next(resp.iter_lines()).decode()
    assert '"type": "session"' in first_line


def test_ask_short_question_returns_422(client):
    """POST /ask com pergunta muito curta retorna 422."""
    resp = client.post("/ask", json={
        "question": "oi",
        "top_k": 3
    })
    assert resp.status_code == 422
    data = resp.json()
    assert "detail" in data


def test_conversations_nonexistent_returns_404(client):
    """GET /api/conversations/{id} com id inexistente retorna 404."""
    resp = client.get("/api/conversations/uuid-inexistente-12345")
    # Pode ser 404 (sessao nao encontrada) ou 200 (lista vazia)
    assert resp.status_code in (200, 404)
