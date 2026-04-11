"""Catálogo de documentos em SQLite.

Implementa :class:`DocumentCatalog` usando a mesma ``metadata.db`` do
``SQLiteMetadataStore`` (tabelas diferentes, mesmo arquivo).

Tabela ``documents``:
    doc_id      – identificador único derivado do hash SHA-256
    source_name – nome original do arquivo (para exibição/citação)
    file_hash   – SHA-256 do conteúdo binário (garante idempotência)
    seguradora  – nome da seguradora
    ano         – ano do documento
    tipo        – tipo do documento
    ramo        – ramo de seguro (ex: Agricola, Automovel, PME…)
    chunk_count – quantidade de chunks indexados no FAISS
    created_at  – data/hora da primeira indexação (ISO 8601 UTC)
"""
import sqlite3
from typing import List, Optional

from app.domain.entities.document import DocumentRecord
from app.domain.interfaces.document_catalog import DocumentCatalog


class SQLiteDocumentCatalog(DocumentCatalog):
    """Implementação SQLite do catálogo de documentos."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._init_db()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    doc_id      TEXT    PRIMARY KEY,
                    source_name TEXT    NOT NULL,
                    file_hash   TEXT    NOT NULL UNIQUE,
                    seguradora  TEXT    NOT NULL DEFAULT 'Desconhecida',
                    ano         INTEGER NOT NULL DEFAULT 0,
                    tipo        TEXT    NOT NULL DEFAULT 'Geral',
                    ramo        TEXT    NOT NULL DEFAULT 'Desconhecido',
                    chunk_count INTEGER NOT NULL DEFAULT 0,
                    created_at  TEXT    NOT NULL
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_doc_file_hash ON documents(file_hash)"
            )

    # ------------------------------------------------------------------
    # DocumentCatalog interface
    # ------------------------------------------------------------------

    def register(self, record: DocumentRecord) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO documents "
                "(doc_id, source_name, file_hash, seguradora, ano, tipo, ramo, chunk_count, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record.doc_id,
                    record.source_name,
                    record.file_hash,
                    record.seguradora,
                    record.ano,
                    record.tipo,
                    record.ramo,
                    record.chunk_count,
                    record.created_at,
                ),
            )

    def find_by_hash(self, file_hash: str) -> Optional[DocumentRecord]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM documents WHERE file_hash = ?", (file_hash,)
            ).fetchone()
        return DocumentRecord(**dict(row)) if row else None

    def update_metadata(
        self, doc_id: str, seguradora: str, ano: int, tipo: str, ramo: str
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE documents SET seguradora=?, ano=?, tipo=?, ramo=? WHERE doc_id=?",
                (seguradora, ano, tipo, ramo, doc_id),
            )

    def remove(self, doc_id: str) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM documents WHERE doc_id = ?", (doc_id,))

    def list_all(self) -> List[DocumentRecord]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM documents ORDER BY seguradora ASC, ano DESC"
            ).fetchall()
        return [DocumentRecord(**dict(row)) for row in rows]

    def total_chunks(self) -> int:
        with self._conn() as conn:
            result = conn.execute(
                "SELECT COALESCE(SUM(chunk_count), 0) FROM documents"
            ).fetchone()
        return result[0]
