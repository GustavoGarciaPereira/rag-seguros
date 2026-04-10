from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from app.domain.entities.document import Chunk, InsuranceMetadata, SearchResult


class VectorRepository(ABC):
    """Repositório de vetores: armazena e recupera chunks por similaridade semântica.

    Esta interface é agnóstica à implementação subjacente (FAISS, Chroma, Pinecone…).
    Todo o chunking e reranking ocorrem *fora* deste contrato — o repositório
    recebe chunks prontos e devolve resultados brutos ordenados por distância vetorial.
    """

    @abstractmethod
    def add(self, chunks: List[Chunk]) -> None:
        """Adiciona *chunks* ao índice vetorial e persiste."""
        ...

    @abstractmethod
    def search(
        self,
        query: str,
        n_results: int = 10,
        filter_dict: Optional[Dict[str, Any]] = None,
    ) -> List[SearchResult]:
        """Busca os *n_results* chunks mais próximos de *query*.

        Se *filter_dict* for fornecido, apenas chunks cujos metadados
        satisfaçam todos os pares chave-valor serão retornados.
        """
        ...

    @abstractmethod
    def delete(self, document_id: str) -> int:
        """Remove todos os chunks do documento *document_id*.

        Returns:
            Quantidade de chunks removidos.
        """
        ...

    @abstractmethod
    def has_document(self, document_id: str) -> bool:
        """Retorna True se o documento já está indexado."""
        ...

    @abstractmethod
    def update_metadata(self, document_id: str, metadata: InsuranceMetadata) -> bool:
        """Atualiza os metadados de seguro de um documento sem re-indexar embeddings.

        Útil quando apenas seguradora/ano/tipo mudam para um arquivo idêntico.

        Returns:
            True se o documento existia e foi atualizado.
        """
        ...

    @abstractmethod
    def count(self) -> int:
        """Total de chunks indexados."""
        ...
