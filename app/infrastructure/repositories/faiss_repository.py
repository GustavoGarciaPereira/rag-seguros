"""Repositório vetorial FAISS + metadados SQLite.

Esta classe implementa :class:`VectorRepository` e é a única do sistema que
conhece FAISS e SentenceTransformers.  Toda a lógica de chunking, parsing e
reranking foi extraída para as camadas de domínio/infra específicas.

Fluxo interno:
1. ``add``   → encode textos → ``index.add`` → ``SQLiteMetadataStore.insert_many``
2. ``search`` → encode query → ``index.search`` → lookup de metadata no SQLite
3. ``delete`` → ``SQLiteMetadataStore.delete_document`` → reconstrução do índice FAISS
"""
import logging
import os
from typing import Any, Dict, List, Optional

import faiss
from sentence_transformers import SentenceTransformer

from app.domain.entities.document import Chunk, InsuranceMetadata, SearchResult
from app.domain.interfaces.vector_repository import VectorRepository
from app.infrastructure.repositories.sqlite_metadata import SQLiteMetadataStore

logger = logging.getLogger("rag")


class FAISSVectorRepository(VectorRepository):
    """Implementação FAISS + SQLite do repositório vetorial."""

    EMBEDDING_MODEL = "all-MiniLM-L6-v2"
    EMBEDDING_DIM = 384

    def __init__(self, persist_directory: str = "./faiss_db") -> None:
        self.persist_directory = persist_directory
        os.makedirs(persist_directory, exist_ok=True)

        self._embedding_model: Optional[SentenceTransformer] = None

        self.index_path = os.path.join(persist_directory, "faiss_index.bin")
        db_path = os.path.join(persist_directory, "metadata.db")
        self._meta = SQLiteMetadataStore(db_path)

        # Carrega índice FAISS existente ou cria um novo
        if os.path.exists(self.index_path):
            self.index = faiss.read_index(self.index_path)
        else:
            self.index = faiss.IndexFlatL2(self.EMBEDDING_DIM)

        # Migração automática a partir do pickle legado (executa apenas uma vez)
        legacy_pickle = os.path.join(persist_directory, "metadata.pkl")
        if not self._meta.has_any_data() and os.path.exists(legacy_pickle):
            migrated = self._meta.migrate_from_pickle(legacy_pickle)
            if migrated:
                logger.info("Migração de %d chunks do pickle legado para SQLite.", migrated)

    # ------------------------------------------------------------------
    # Lazy model loading (evita bloquear startup ~60 s no cold start)
    # ------------------------------------------------------------------

    @property
    def embedding_model(self) -> SentenceTransformer:
        if self._embedding_model is None:
            self._embedding_model = SentenceTransformer(self.EMBEDDING_MODEL)
        return self._embedding_model

    def warm_up(self) -> None:
        """Pré-carrega o modelo de embeddings.  Chamado no startup do FastAPI."""
        _ = self.embedding_model.encode("warm up")

    # ------------------------------------------------------------------
    # VectorRepository interface
    # ------------------------------------------------------------------

    def add(self, chunks: List[Chunk]) -> None:
        if not chunks:
            return
        texts = [c.text for c in chunks]
        entries = [
            (
                c.text,
                {
                    "doc_id": c.document_id,
                    "source": c.source,
                    "page": c.page,
                    "seguradora": c.metadata.seguradora,
                    "ano": c.metadata.ano,
                    "tipo": c.metadata.tipo,
                    "ramo": c.metadata.ramo,
                    "chunk_index": c.chunk_index,
                },
            )
            for c in chunks
        ]
        embeddings = self.embedding_model.encode(texts).astype("float32")
        self.index.add(embeddings)
        self._meta.insert_many(entries)
        faiss.write_index(self.index, self.index_path)

    def search(
        self,
        query: str,
        n_results: int = 10,
        filter_dict: Optional[Dict[str, Any]] = None,
    ) -> List[SearchResult]:
        if self.index.ntotal == 0:
            return []

        # Busca mais candidatos quando há filtro, para compensar o pós-filtro
        search_k = min(n_results * 5 if filter_dict else n_results, self.index.ntotal)

        query_embedding = self.embedding_model.encode([query]).astype("float32")
        distances, indices = self.index.search(query_embedding, search_k)

        results: List[SearchResult] = []
        for idx, distance in zip(indices[0], distances[0]):
            if idx < 0:
                continue
            meta = self._meta.get_by_faiss_pos(int(idx))
            if meta is None:
                continue

            if filter_dict and any(
                meta.get(k) != v for k, v in filter_dict.items()
            ):
                continue

            results.append(
                SearchResult(
                    text=meta["text"],
                    source=meta["source"],
                    page=meta.get("page", 0),
                    seguradora=meta.get("seguradora", "Desconhecida"),
                    ano=meta.get("ano", 0),
                    tipo=meta.get("tipo", "Geral"),
                    ramo=meta.get("ramo", "Desconhecido"),
                    relevance_score=float(1 / (1 + distance)),
                )
            )

            if len(results) >= n_results:
                break

        return results

    def delete(self, document_id: str) -> int:
        removed, remaining_texts = self._meta.delete_document(document_id)
        if removed == 0:
            return 0

        # Reconstrói o índice FAISS sem os chunks removidos
        self.index = faiss.IndexFlatL2(self.EMBEDDING_DIM)
        if remaining_texts:
            embeddings = self.embedding_model.encode(remaining_texts).astype("float32")
            self.index.add(embeddings)

        faiss.write_index(self.index, self.index_path)
        return removed

    def update_metadata(self, document_id: str, metadata: InsuranceMetadata) -> bool:
        return self._meta.update_document_metadata(
            document_id, metadata.seguradora, metadata.ano, metadata.tipo, metadata.ramo
        )

    def has_document(self, document_id: str) -> bool:
        return self._meta.has_document(document_id)

    def count(self) -> int:
        return self.index.ntotal

    # ------------------------------------------------------------------
    # Extra helpers (usados por health/metrics routes)
    # ------------------------------------------------------------------

    def get_collection_stats(self) -> Dict[str, Any]:
        return {
            "total_chunks": self.index.ntotal,
            "persist_directory": self.persist_directory,
            "embedding_dim": self.EMBEDDING_DIM,
        }
