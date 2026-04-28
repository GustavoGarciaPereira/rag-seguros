from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Tuple


class ChatHistory(ABC):
    """Histórico de conversas indexado por session_id.

    Isola o armazenamento de conversas do resto do sistema.
    """

    @abstractmethod
    def add_message(self, session_id: str, role: str, content: str) -> None:
        """Adiciona uma mensagem à sessão.

        Args:
            session_id: Identificador da sessão.
            role: ``"user"`` ou ``"assistant"``.
            content: Texto da mensagem.
        """
        ...

    @abstractmethod
    def get_recent_messages(
        self, session_id: str, limit: int = 10
    ) -> List[Tuple[str, str]]:
        """Retorna as últimas *limit* mensagens da sessão, em ordem cronológica.

        Args:
            session_id: Identificador da sessão.
            limit: Número máximo de mensagens a retornar (default 10 = 5 trocas).

        Returns:
            Lista de tuplas ``(role, content)`` ordenada do mais antigo ao mais recente.
        """
        ...

    @abstractmethod
    def get_messages(self, session_id: str) -> List[Dict[str, str]]:
        """Retorna todas as mensagens da sessão com timestamps.

        Args:
            session_id: Identificador da sessão.

        Returns:
            Lista de dicts ``{"role": "...", "content": "...", "timestamp": "..."}``
            em ordem cronológica.
        """
        ...
