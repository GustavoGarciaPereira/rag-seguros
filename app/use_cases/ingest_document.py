"""Use Case: IngestDocument.

Orquestra o fluxo completo de ingestão de um documento:
    Parse → Chunk → (Dedup via hash) → Add ao repositório vetorial → Registrar no catálogo.

Toda a lógica de negócio — divisão semântica, overlaps entre páginas,
cálculo de página por offset, deduplicação por conteúdo — vive aqui,
fora de qualquer classe de infraestrutura.
"""
import hashlib
import logging
import os
from datetime import datetime, timezone
from typing import List

from app.domain.entities.document import Chunk, DocumentRecord, InsuranceMetadata
from app.domain.interfaces.document_catalog import DocumentCatalog
from app.domain.interfaces.document_parser import DocumentParser
from app.domain.interfaces.text_chunker import TextChunker
from app.domain.interfaces.vector_repository import VectorRepository

logger = logging.getLogger("rag")

_DEFAULT_CHUNK_SIZE = 1200
_DEFAULT_OVERLAP = 200


class IngestDocument:
    """Processa e indexa um arquivo PDF no repositório vetorial.

    Recebe todas as dependências via injeção — desconhece FAISS, pypdf ou
    qualquer implementação concreta.

    Lógica de deduplicação (baseada em SHA-256 do conteúdo):
    - Hash já existe + metadados idênticos  → skip (retorna chunk_count existente)
    - Hash já existe + metadados diferentes → atualiza metadados sem re-embedar
    - Hash novo                             → processa e indexa do zero
    """

    def __init__(
        self,
        parser: DocumentParser,
        chunker: TextChunker,
        vector_repo: VectorRepository,
        catalog: DocumentCatalog,
    ) -> None:
        self._parser = parser
        self._chunker = chunker
        self._vector_repo = vector_repo
        self._catalog = catalog

    def execute(
        self,
        file_path: str,
        metadata: InsuranceMetadata,
        source_name: str = "",
        chunk_size: int = _DEFAULT_CHUNK_SIZE,
        overlap: int = _DEFAULT_OVERLAP,
    ) -> int:
        """Indexa o documento em *file_path*.

        Args:
            file_path:   Caminho para o arquivo no disco (pode ser temporário).
            metadata:    Metadados de negócio (seguradora, ano, tipo).
            source_name: Nome original do arquivo (para citações e inventário).
                         Quando omitido, usa ``basename(file_path)``.
            chunk_size:  Tamanho-alvo de cada chunk em caracteres.
            overlap:     Sobreposição entre chunks adjacentes.

        Returns:
            Número de chunks no índice após a operação
            (existentes se skip/update, novos se re-indexação).

        Raises:
            ValueError: Se o documento não tiver texto extraível.
        """
        file_hash = self._hash_file(file_path)
        doc_id = self._make_doc_id(file_path, file_hash)
        citation_source = source_name or os.path.basename(file_path)

        # --- Deduplicação por hash SHA-256 ---
        existing = self._catalog.find_by_hash(file_hash)
        if existing is not None:
            metadata_changed = (
                metadata.seguradora != existing.seguradora
                or metadata.ano != existing.ano
                or metadata.tipo != existing.tipo
                or metadata.ramo != existing.ramo
            )
            if not metadata_changed:
                logger.info(
                    "'%s' já indexado e inalterado — skip.",
                    citation_source,
                )
                return existing.chunk_count

            # Mesmo conteúdo, metadados novos: atualiza sem re-embedar
            self._catalog.update_metadata(
                existing.doc_id, metadata.seguradora, metadata.ano, metadata.tipo, metadata.ramo
            )
            self._vector_repo.update_metadata(existing.doc_id, metadata)
            logger.info(
                "Metadados de '%s' atualizados sem re-indexação (%s / %d / %s).",
                citation_source,
                metadata.seguradora,
                metadata.ano,
                metadata.tipo,
            )
            return existing.chunk_count

        # --- Novo documento (ou re-upload forçado) ---
        # Remove versão anterior pelo doc_id caso exista no FAISS
        removed = self._vector_repo.delete(doc_id)
        if removed > 0:
            self._catalog.remove(doc_id)
            logger.info(
                "Versão anterior de '%s' removida — %d chunks.", citation_source, removed
            )

        pages = self._parser.parse(file_path)
        if not pages:
            raise ValueError("Não foi possível extrair texto do PDF")

        chunks: List[Chunk] = []
        previous_tail = ""

        for parsed_page in pages:
            tail_len = len(previous_tail)
            combined_text = previous_tail + parsed_page.text

            raw_chunks = self._chunker.chunk(
                combined_text, chunk_size=chunk_size, overlap=overlap
            )

            for chunk_text, start_pos in raw_chunks:
                # Atribui página pelo ponto médio do chunk:
                # se o meio cair dentro do tail → página anterior.
                chunk_mid = start_pos + len(chunk_text) // 2
                assigned_page = (
                    parsed_page.page_number - 1
                    if tail_len > 0 and chunk_mid < tail_len
                    else parsed_page.page_number
                )

                chunks.append(
                    Chunk(
                        text=chunk_text,
                        source=citation_source,
                        document_id=doc_id,
                        page=assigned_page,
                        chunk_index=len(chunks),
                        metadata=metadata,
                    )
                )

            previous_tail = (
                parsed_page.text[-overlap:]
                if len(parsed_page.text) > overlap
                else parsed_page.text
            )

        if not chunks:
            raise ValueError("Não foi possível extrair texto do PDF")

        logger.info(
            "Documento '%s' dividido em %d chunks (%d páginas).",
            citation_source,
            len(chunks),
            len(pages),
        )

        self._vector_repo.add(chunks)
        self._catalog.register(
            DocumentRecord(
                doc_id=doc_id,
                source_name=citation_source,
                file_hash=file_hash,
                seguradora=metadata.seguradora,
                ano=metadata.ano,
                tipo=metadata.tipo,
                ramo=metadata.ramo,
                chunk_count=len(chunks),
                created_at=datetime.now(timezone.utc).isoformat(),
            )
        )
        return len(chunks)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _hash_file(file_path: str) -> str:
        """SHA-256 do conteúdo binário — identidade do documento."""
        with open(file_path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()

    @staticmethod
    def _make_doc_id(file_path: str, file_hash: str) -> str:
        """ID derivado do nome do arquivo + primeiros 12 chars do SHA-256."""
        return f"{os.path.basename(file_path)}_{file_hash[:12]}"
