from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from app.domain.interfaces.chat_history import ChatHistory


class SQLiteChatHistory(ChatHistory):
    """Histórico de conversas persistido em SQLite.

    Cada linha na tabela ``messages`` representa uma mensagem isolada.
    O banco é thread-safe via um lock por operação de escrita.
    """

    def __init__(self, db_path: str = "") -> None:
        self._db_path = db_path or os.path.join("faiss_db", "chat_history.db")
        self._lock = threading.Lock()
        self._ensure_table()

    # ------------------------------------------------------------------
    # ChatHistory interface
    # ------------------------------------------------------------------

    def add_message(self, session_id: str, role: str, content: str) -> None:
        if role not in ("user", "assistant"):
            raise ValueError(f"role inválido: {role!r} — use 'user' ou 'assistant'")
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            try:
                conn = sqlite3.connect(self._db_path)
                conn.execute(
                    "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                    (session_id, role, content, now),
                )
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
