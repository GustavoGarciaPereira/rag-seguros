from abc import ABC, abstractmethod
from typing import List

from app.domain.entities.document import SearchResult


class Reranker(ABC):
    """Estratégia de re-ranqueamento de resultados de busca vetorial."""

    @abstractmethod
    def rerank(self, query: str, results: List[SearchResult]) -> List[SearchResult]:
        """Re-ordena *results* em função da relevância para *query*."""
        ...
