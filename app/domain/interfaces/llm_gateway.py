from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from app.domain.entities.document import SearchResult


class LLMGateway(ABC):
    """Gateway para o modelo de linguagem remoto.

    Isola a lógica de negócio de qualquer SDK ou provider concreto.
    """

    @abstractmethod
    def generate(
        self,
        question: str,
        context: List[SearchResult],
        seguradora: Optional[str] = None,
        document_type: Optional[str] = None,
    ) -> str:
        """Gera resposta estruturada a partir do *context* recuperado."""
        ...

    @abstractmethod
    def test_connection(self) -> tuple[bool, str]:
        """Verifica conectividade com o provider remoto.

        Returns:
            (success, message)
        """
        ...
