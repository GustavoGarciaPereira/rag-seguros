from functools import lru_cache

from app.services.llm_service import LLMService
from app.services.vector_service import FAISSStore
from app.services.document_service import DocumentService


@lru_cache(maxsize=1)
def _vector_service() -> FAISSStore:
    return FAISSStore()


@lru_cache(maxsize=1)
def _llm_service() -> LLMService:
    return LLMService()


def get_vector_service() -> FAISSStore:
    return _vector_service()


def get_llm_service() -> LLMService:
    return _llm_service()


def get_document_service() -> DocumentService:
    return DocumentService(_vector_service())
