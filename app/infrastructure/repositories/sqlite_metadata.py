"""Armazenamento de metadados e textos de chunks em SQLite.

Substitui o pickle usado pelo FAISSStore legado.  Cada linha mapeia uma
posição no índice FAISS (faiss_pos) para o texto e metadados do chunk.

Responsabilidades:
- Persistir metadados e textos dos chunks.
- Manter faiss_pos sincronizado com o índice FAISS após remoções.
- Fornecer migração automática a partir do pickle legado na primeira carga.
"""
import sqlite3
from typing import Any, Dict, List, Optional, Tuple


class SQLiteMetadataStore:
    """Store leve de metadados de chunks, sem dependências externas."""

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
                CREATE TABLE IF NOT EXISTS chunks (
                    faiss_pos   INTEGER NOT NULL,
                    doc_id      TEXT    NOT NULL,
                    text        TEXT    NOT NULL,
                    source      TEXT    NOT NULL DEFAULT '',
                    page        INTEGER NOT NULL DEFAULT 0,
                    seguradora  TEXT    NOT NULL DEFAULT 'Desconhecida' COLLATE NOCASE,
                    ano         INTEGER NOT NULL DEFAULT 0,
                    tipo        TEXT    NOT NULL DEFAULT 'Geral',
                    ramo        TEXT    NOT NULL DEFAULT 'Desconhecido' COLLATE NOCASE,
                    chunk_index INTEGER NOT NULL DEFAULT 0
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_doc_id  ON chunks(doc_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_faiss_pos ON chunks(faiss_pos)"
            )

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def insert_many(self, entries: List[Tuple[str, Dict[str, Any]]]) -> None:
        """Insere pares (text, metadata) atribuindo faiss_pos sequenciais.

        Os novos chunks são acrescentados *após* o último faiss_pos existente,
        mantendo a correspondência com o índice FAISS que foi expandido com
        ``index.add()``.
        """
        if not entries:
            return
        with self._conn() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(faiss_pos) + 1, 0) FROM chunks"
            ).fetchone()
            next_pos: int = row[0]

            rows = [
                (
                    next_pos + i,
                    meta["doc_id"],
                    text,
                    meta.get("source", ""),
                    meta.get("page", 0),
                    meta.get("seguradora", "Desconhecida"),
                    meta.get("ano", 0),
                    meta.get("tipo", "Geral"),
                    meta.get("ramo", "Desconhecido"),
                    meta.get("chunk_index", 0),
                )
                for i, (text, meta) in enumerate(entries)
            ]
            conn.executemany(
                "INSERT INTO chunks "
                "(faiss_pos, doc_id, text, source, page, seguradora, ano, tipo, ramo, chunk_index) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_by_faiss_pos(self, pos: int) -> Optional[Dict[str, Any]]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM chunks WHERE faiss_pos = ?", (pos,)
            ).fetchone()
        return dict(row) if row else None

    def has_document(self, doc_id: str) -> bool:
        with self._conn() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM chunks WHERE doc_id = ?", (doc_id,)
            ).fetchone()[0]
        return count > 0

    def has_any_data(self) -> bool:
        with self._conn() as conn:
            return conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] > 0

    def count(self) -> int:
        with self._conn() as conn:
            return conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update_document_metadata(
        self, doc_id: str, seguradora: str, ano: int, tipo: str, ramo: str
    ) -> bool:
        """Atualiza metadados de seguro de todos os chunks de um documento.

        Não altera embeddings — só os campos de metadados no SQLite.

        Returns:
            True se ao menos um chunk foi atualizado.
        """
        with self._conn() as conn:
            cursor = conn.execute(
                "UPDATE chunks SET seguradora=?, ano=?, tipo=?, ramo=? WHERE doc_id=?",
                (seguradora, ano, tipo, ramo, doc_id),
            )
        return cursor.rowcount > 0

    # ------------------------------------------------------------------
    # Delete + renumber
    # ------------------------------------------------------------------

    def delete_document(self, doc_id: str) -> Tuple[int, List[str]]:
        """Remove os chunks do documento e renumera faiss_pos nos restantes.

        Após a chamada, os faiss_pos dos chunks restantes são 0-indexados e
        contíguos — prontos para o índice FAISS reconstruído.

        Returns:
            (removed_count, remaining_texts_in_new_faiss_order)
        """
        with self._conn() as conn:
            removed: int = conn.execute(
                "SELECT COUNT(*) FROM chunks WHERE doc_id = ?", (doc_id,)
            ).fetchone()[0]

            if removed == 0:
                return 0, []

            # Captura textos restantes na ordem original (faiss_pos ASC)
            remaining_rows = conn.execute(
                "SELECT rowid, text FROM chunks WHERE doc_id != ? ORDER BY faiss_pos",
                (doc_id,),
            ).fetchall()

            # Remove o documento
            conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))

            # Renumera: cada chunk restante recebe o seu novo índice no FAISS
            if remaining_rows:
                conn.executemany(
                    "UPDATE chunks SET faiss_pos = ? WHERE rowid = ?",
                    [(new_pos, row["rowid"]) for new_pos, row in enumerate(remaining_rows)],
                )

        return removed, [row["text"] for row in remaining_rows]

    def truncate_all(self) -> None:
        """Remove todos os chunks da tabela.

        Usado por :meth:`FAISSVectorRepository.delete_all` antes de uma
        re-indexação completa.  O próximo ``insert_many`` partirá de
        ``faiss_pos = 0`` automaticamente (``COALESCE(MAX+1, 0)``).
        """
        with self._conn() as conn:
            conn.execute("DELETE FROM chunks")

    # ------------------------------------------------------------------
    # Migration from legacy pickle
    # ------------------------------------------------------------------

    def migrate_from_pickle(self, pickle_path: str) -> int:
        """Importa metadados do pickle legado para o SQLite na primeira carga.

        Returns:
            Número de chunks migrados.
        """
        import pickle

        with open(pickle_path, "rb") as f:
            data = pickle.load(f)

        metadata: List[Dict[str, Any]] = data.get("metadata", [])
        texts: List[str] = data.get("document_texts", [])

        if not metadata or not texts:
            return 0

        entries: List[Tuple[str, Dict[str, Any]]] = [
            (
                text,
                {
                    "doc_id": meta.get("document_id", "legacy_unknown"),
                    "source": meta.get("source", ""),
                    "page": meta.get("page", 0),
                    "seguradora": meta.get("seguradora", "Desconhecida"),
                    "ano": meta.get("ano", 0),
                    "tipo": meta.get("tipo", "Geral"),
                    "chunk_index": meta.get("chunk_index", 0),
                },
            )
            for text, meta in zip(texts, metadata)
        ]
        self.insert_many(entries)
        return len(entries)
