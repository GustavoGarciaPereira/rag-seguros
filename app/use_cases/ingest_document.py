"""Use Case: IngestDocument.

Orquestra o fluxo completo de ingestão de um documento:
    Parse → Chunk → (Dedup) → Add ao repositório vetorial.

Toda a lógica de negócio — divisão semântica, overlaps entre páginas,
cálculo de página por offset — vive aqui, fora de qualquer classe de
infraestrutura.
"""
import hashlib
import logging
import os
from typing import List

from app.domain.entities.document import Chunk, InsuranceMetadata
from app.domain.interfaces.document_parser import DocumentParser
from app.domain.interfaces.text_chunker import TextChunker
from app.domain.interfaces.vector_repository import VectorRepository

logger = logging.getLogger("rag")

_DEFAULT_CHUNK_SIZE = 1200
_DEFAULT_OVERLAP = 200


class IngestDocument:
    """Processa e indexa um arquivo PDF no repositório vetorial.

    Recebe as interfaces via injeção de dependência — desconhece FAISS,
    pypdf ou qualquer implementação concreta.
    """

    def __init__(
        self,
        parser: DocumentParser,
        chunker: TextChunker,
        vector_repo: VectorRepository,
    ) -> None:
        self._parser = parser
        self._chunker = chunker
        self._vector_repo = vector_repo

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
            file_path:   Caminho para o arquivo temporário no disco.
            metadata:    Metadados de negócio (seguradora, ano, tipo).
            source_name: Nome original do arquivo (usado para citações).
                         Quando omitido, usa ``basename(file_path)``.
            chunk_size:  Tamanho-alvo de cada chunk em caracteres.
            overlap:     Sobreposição entre chunks adjacentes.

        Returns:
            Número de chunks adicionados ao repositório.

        Raises:
            ValueError: Se o documento não tiver texto extraível.
        """
        doc_id = self._generate_doc_id(file_path)
        citation_source = source_name or os.path.basename(file_path)

        # Deduplicação: remove versão anterior antes de reindexar
        removed = self._vector_repo.delete(doc_id)
        if removed > 0:
            logger.info("Documento '%s' já existia — %d chunks removidos.", citation_source, removed)

        pages = self._parser.parse(file_path)
        if not pages:
            raise ValueError("Não foi possível extrair texto do PDF")

        chunks: List[Chunk] = []
        previous_tail = ""

        for parsed_page in pages:
            tail_len = len(previous_tail)
            combined_text = previous_tail + parsed_page.text

            raw_chunks = self._chunker.chunk(combined_text, chunk_size=chunk_size, overlap=overlap)

            for chunk_text, start_pos in raw_chunks:
                # Atribui página pelo ponto médio do chunk:
                # se o meio cair dentro do tail, pertence à página anterior.
                chunk_mid = start_pos + len(chunk_text) // 2
                if tail_len > 0 and chunk_mid < tail_len:
                    assigned_page = parsed_page.page_number - 1
                else:
                    assigned_page = parsed_page.page_number

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

            # Guarda o final da página para overlap com a próxima
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
        return len(chunks)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_doc_id(file_path: str) -> str:
        """ID único baseado no conteúdo (MD5) — garante deduplicação."""
        with open(file_path, "rb") as f:
            content_hash = hashlib.md5(f.read()).hexdigest()
        return f"{os.path.basename(file_path)}_{content_hash[:8]}"
