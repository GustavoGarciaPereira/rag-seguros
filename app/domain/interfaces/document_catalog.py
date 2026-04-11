from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from app.domain.entities.document import DocumentRecord


class DocumentCatalog(ABC):
    """Catálogo de documentos indexados.

    Rastreia metadados, hash SHA-256 e chunk_count por arquivo — separado do
    repositório vetorial, que lida apenas com chunks e embeddings.
    """

    @abstractmethod
    def register(self, record: DocumentRecord) -> None:
        """Registra (ou substitui) um documento no catálogo."""
        ...

    @abstractmethod
    def find_by_hash(self, file_hash: str) -> Optional[DocumentRecord]:
        """Retorna o registro pelo hash SHA-256, ou None se não existir."""
        ...

    @abstractmethod
    def update_metadata(
        self, doc_id: str, seguradora: str, ano: int, tipo: str, ramo: str
    ) -> None:
        """Atualiza apenas os campos de metadados de seguro, sem alterar hash ou chunks."""
        ...

    @abstractmethod
    def remove(self, doc_id: str) -> None:
        """Remove o registro do catálogo."""
        ...

    @abstractmethod
    def list_all(self) -> List[DocumentRecord]:
        """Retorna todos os documentos registrados, ordenados por seguradora e ano desc."""
        ...

    @abstractmethod
    def total_chunks(self) -> int:
        """Soma de chunk_count de todos os documentos registrados."""
        ...
