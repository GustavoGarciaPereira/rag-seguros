from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple

from app.domain.interfaces.chat_history import ChatHistory


class SQLiteChatHistory(ChatHistory):
    """Histórico de conversas persistido em SQLite.

    Cada linha na tabela ``messages`` representa uma mensagem isolada.
    O banco é thread-safe via um lock por operação de escrita.
    Mensagens mais antigas que ``retention_days`` são removidas
    automaticamente a cada escrita (purge por janela deslizante).
    """

    def __init__(self, db_path: str = "", retention_days: int = 30) -> None:
        self._db_path = db_path or os.path.join("faiss_db", "chat_history.db")
        self._retention_days = retention_days
        self._lock = threading.Lock()
        self._ensure_table()

    # ------------------------------------------------------------------
    # ChatHistory interface
    # ------------------------------------------------------------------

    def add_message(self, session_id: str, role: str, content: str) -> None:
        if role not in ("user", "assistant"):
            raise ValueError(f"role inválido: {role!r} — use 'user' ou 'assistant'")
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        # Cutoff derivado do MESMO instante do INSERT — garante que a mensagem
        # recém-gravada nunca seja apagada (mesmo com retention_days=0)
        cutoff_iso = (now - timedelta(days=self._retention_days)).isoformat()
        with self._lock:
            try:
                conn = sqlite3.connect(self._db_path)
                conn.execute("PRAGMA busy_timeout=5000")
                conn.execute(
                    "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                    (session_id, role, content, now_iso),
                )
                # Purge por retenção (janela deslizante) — impede crescimento sem teto
                conn.execute("DELETE FROM messages WHERE created_at < ?", (cutoff_iso,))
                conn.commit()
            finally:
                conn.close()

    def get_recent_messages(
        self, session_id: str, limit: int = 10
    ) -> List[Tuple[str, str]]:
        with self._lock:
            try:
                conn = sqlite3.connect(self._db_path)
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                    (session_id, limit),
                ).fetchall()
            finally:
                conn.close()
        # Reorder chronologically (oldest first)
        return [(r["role"], r["content"]) for r in reversed(rows)]

    def get_messages(self, session_id: str) -> List[Dict[str, str]]:
        with self._lock:
            try:
                conn = sqlite3.connect(self._db_path)
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT role, content, created_at FROM messages WHERE session_id = ? ORDER BY id ASC",
                    (session_id,),
                ).fetchall()
            finally:
                conn.close()
        return [
            {"role": r["role"], "content": r["content"], "timestamp": r["created_at"]}
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _ensure_table(self) -> None:
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        with self._lock:
            try:
                conn = sqlite3.connect(self._db_path)
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA busy_timeout=5000")
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS messages (
                        id          INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id  TEXT    NOT NULL,
                        role        TEXT    NOT NULL,
                        content     TEXT    NOT NULL,
                        created_at  TEXT    NOT NULL
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_messages_session ON messages (session_id, id)"
                )
                conn.commit()
            finally:
                conn.close()
