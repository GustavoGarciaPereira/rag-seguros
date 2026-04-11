"""Injeção de dependência via FastAPI Depends + lru_cache.

Cada singleton é instanciado na primeira chamada e reutilizado por todas as
requests subsequentes.  As rotas recebem use cases prontos — nunca objetos
de infraestrutura diretamente.
"""
import os
from functools import lru_cache

from app.infrastructure.chunkers.semantic_chunker import InsuranceSemanticChunker
from app.infrastructure.gateways.deepseek_gateway import DeepSeekGateway
from app.infrastructure.parsers.pdf_parser import PdfDocumentParser
from app.infrastructure.rerankers.keyword_reranker import KeywordOverlapReranker
from app.infrastructure.repositories.faiss_repository import FAISSVectorRepository
from app.infrastructure.repositories.sqlite_catalog import SQLiteDocumentCatalog
from app.use_cases.answer_question import AskInsuranceQuestion
from app.use_cases.get_inventory import GetInventory
from app.use_cases.ingest_document import IngestDocument

_DB_PATH = os.path.join("faiss_db", "metadata.db")

# ------------------------------------------------------------------
# Singletons de infraestrutura
# ------------------------------------------------------------------


@lru_cache(maxsize=1)
def _vector_repo() -> FAISSVectorRepository:
    return FAISSVectorRepository()


@lru_cache(maxsize=1)
def _llm_gateway() -> DeepSeekGateway:
    return DeepSeekGateway()


@lru_cache(maxsize=1)
def _chunker() -> InsuranceSemanticChunker:
    return InsuranceSemanticChunker()


@lru_cache(maxsize=1)
def _reranker() -> KeywordOverlapReranker:
    return KeywordOverlapReranker()


@lru_cache(maxsize=1)
def _parser() -> PdfDocumentParser:
    return PdfDocumentParser()


@lru_cache(maxsize=1)
def _document_catalog() -> SQLiteDocumentCatalog:
    os.makedirs("faiss_db", exist_ok=True)
    return SQLiteDocumentCatalog(_DB_PATH)


# ------------------------------------------------------------------
# Use Cases (injetados nas rotas via Depends)
# ------------------------------------------------------------------


def get_ask_use_case() -> AskInsuranceQuestion:
    return AskInsuranceQuestion(_vector_repo(), _reranker(), _llm_gateway())


def get_ingest_use_case() -> IngestDocument:
    return IngestDocument(_parser(), _chunker(), _vector_repo(), _document_catalog())


def get_inventory_use_case() -> GetInventory:
    return GetInventory(_document_catalog())


# ------------------------------------------------------------------
# Atalhos para rotas de health/metrics que precisam do repositório
# ------------------------------------------------------------------


def get_vector_service() -> FAISSVectorRepository:
    """Mantido para health.py e main.py (startup warm_up)."""
    return _vector_repo()


def get_llm_service() -> DeepSeekGateway:
    """Mantido para health.py (/stats → test_connection)."""
    return _llm_gateway()


def get_document_catalog() -> SQLiteDocumentCatalog:
    """Mantido para health.py (/stats → inventory summary)."""
    return _document_catalog()
