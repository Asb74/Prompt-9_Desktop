import logging
import sqlite3
from datetime import datetime, timezone
from uuid import uuid4

from src.config import settings
from src.database.database import Database


class SessionRepository:
    def __init__(self, database: Database) -> None:
        self.logger = logging.getLogger(__name__)
        self.database = database

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _normalize_model(self, model: str | None) -> str:
        normalizer = getattr(settings, "normalize_model", None)
        if callable(normalizer):
            return normalizer(model)
        return settings.DEFAULT_MODEL

    def list_sessions(self) -> list[dict]:
        with self.database.connect() as conn:
            rows = conn.execute("SELECT * FROM sessions ORDER BY updated_at DESC").fetchall()
        return [dict(row) for row in rows]

    def count_messages(self, session_id: str) -> int:
        try:
            with self.database.connect() as conn:
                row = conn.execute(
                    "SELECT COUNT(*) AS total FROM messages WHERE session_id = ?",
                    (session_id,),
                ).fetchone()
            return int(row["total"]) if row else 0
        except sqlite3.Error:
            self.logger.exception("Error SQLite al contar mensajes de sesión=%s", session_id)
            return 0

    def list_sessions_with_stats(self) -> list[dict]:
        try:
            with self.database.connect() as conn:
                rows = conn.execute(
                    """
                    SELECT
                        s.id,
                        s.title,
                        s.created_at,
                        s.updated_at,
                        s.model,
                        COUNT(m.id) AS message_count
                    FROM sessions s
                    LEFT JOIN messages m ON m.session_id = s.id
                    GROUP BY s.id, s.title, s.created_at, s.updated_at, s.model
                    ORDER BY s.updated_at DESC
                    """
                ).fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error:
            self.logger.exception("Error SQLite al listar sesiones con estadísticas.")
            return []

    def search_sessions(self, query: str = "", date_filter: str = "all") -> list[dict]:
        normalized_query = (query or "").strip()
        normalized_filter = (date_filter or "all").strip().lower()
        if normalized_filter not in {"all", "today", "week", "month"}:
            normalized_filter = "all"

        params: list[str] = []
        where_clauses: list[str] = []

        if normalized_filter == "today":
            where_clauses.append("datetime(s.updated_at) >= datetime('now', 'start of day')")
        elif normalized_filter == "week":
            where_clauses.append("datetime(s.updated_at) >= datetime('now', '-7 days')")
        elif normalized_filter == "month":
            where_clauses.append("datetime(s.updated_at) >= datetime('now', '-30 days')")

        if normalized_query:
            like_term = f"%{normalized_query}%"
            where_clauses.append("(s.title LIKE ? COLLATE NOCASE OR m.content LIKE ? COLLATE NOCASE)")
            params.extend([like_term, like_term])

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        sql = f"""
            SELECT
                s.id,
                s.title,
                s.created_at,
                s.updated_at,
                s.model,
                COUNT(DISTINCT m_all.id) AS message_count
            FROM sessions s
            LEFT JOIN messages m ON m.session_id = s.id
            LEFT JOIN messages m_all ON m_all.session_id = s.id
            {where_sql}
            GROUP BY s.id, s.title, s.created_at, s.updated_at, s.model
            ORDER BY s.updated_at DESC
        """
        try:
            with self.database.connect() as conn:
                rows = conn.execute(sql, params).fetchall()
            results = [dict(row) for row in rows]
            self.logger.info(
                "Búsqueda de sesiones: query='%s' filtro='%s' resultados=%s",
                normalized_query,
                normalized_filter,
                len(results),
            )
            return results
        except sqlite3.Error:
            self.logger.exception(
                "Error SQLite al buscar sesiones: query='%s' filtro='%s'",
                normalized_query,
                normalized_filter,
            )
            return []

    def create_session(self, model: str, title: str = "Nueva sesión") -> dict:
        now = self._now_iso()
        session = {
            "id": str(uuid4()),
            "title": (title or "Nueva sesión").strip() or "Nueva sesión",
            "created_at": now,
            "updated_at": now,
            "model": self._normalize_model(model),
            "messages": [],
        }
        self.save_session(session)
        self.logger.info("Sesión creada: %s", session["id"])
        return session

    def get_session(self, session_id: str) -> dict | None:
        with self.database.connect() as conn:
            row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if not row:
            return None
        session = dict(row)
        session["messages"] = self.get_messages(session_id)
        return session

    def save_session(self, session: dict) -> None:
        now = self._now_iso()
        session_id = session.get("id") or str(uuid4())
        messages = session.get("messages", [])
        payload = {
            "id": session_id,
            "title": (session.get("title") or "Nueva sesión").strip() or "Nueva sesión",
            "created_at": session.get("created_at") or now,
            "updated_at": now,
            "model": self._normalize_model(session.get("model")),
        }
        with self.database.connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions(id, title, created_at, updated_at, model)
                VALUES(:id, :title, :created_at, :updated_at, :model)
                ON CONFLICT(id) DO UPDATE SET
                title=excluded.title,
                updated_at=excluded.updated_at,
                model=excluded.model
                """,
                payload,
            )
            conn.commit()
        if isinstance(messages, list):
            self.replace_messages(session_id, messages)
        session.update(payload)
        session["id"] = session_id
        self.logger.info("Sesión guardada: %s", session_id)

    def delete_session(self, session_id: str) -> None:
        with self.database.connect() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            conn.commit()
        self.logger.info("Sesión eliminada: %s", session_id)

    def rename_session(self, session_id: str, new_title: str) -> None:
        cleaned_title = (new_title or "").strip()
        if not cleaned_title:
            return
        with self.database.connect() as conn:
            conn.execute(
                "UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?",
                (cleaned_title, self._now_iso(), session_id),
            )
            conn.commit()
        self.logger.info("Sesión renombrada: %s", session_id)

    def add_message(self, session_id: str, role: str, content: str, created_at: str | None = None) -> dict | None:
        cleaned_content = (content or "").strip()
        if not cleaned_content:
            return None
        timestamp = created_at or self._now_iso()
        with self.database.connect() as conn:
            position_row = conn.execute(
                "SELECT COALESCE(MAX(position), -1) + 1 AS next_pos FROM messages WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            position = int(position_row["next_pos"])
            message = {
                "id": str(uuid4()),
                "session_id": session_id,
                "role": role,
                "content": cleaned_content,
                "created_at": timestamp,
                "position": position,
            }
            conn.execute(
                """
                INSERT INTO messages(id, session_id, role, content, created_at, position)
                VALUES(:id, :session_id, :role, :content, :created_at, :position)
                """,
                message,
            )
            conn.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (self._now_iso(), session_id))
            conn.commit()
        return message

    def replace_messages(self, session_id: str, messages: list[dict]) -> None:
        with self.database.connect() as conn:
            conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            position = 0
            for msg in messages:
                content = (msg.get("content") or "").strip()
                if not content:
                    continue
                conn.execute(
                    """
                    INSERT OR IGNORE INTO messages(id, session_id, role, content, created_at, position)
                    VALUES(?, ?, ?, ?, ?, ?)
                    """,
                    (
                        msg.get("id") or str(uuid4()),
                        session_id,
                        msg.get("role") or "assistant",
                        content,
                        msg.get("created_at") or self._now_iso(),
                        position,
                    ),
                )
                position += 1
            conn.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (self._now_iso(), session_id))
            conn.commit()

    def add_attachment(self, attachment: dict) -> None:
        try:
            with self.database.connect() as conn:
                conn.execute(
                    """
                    INSERT INTO attachments(
                        id, session_id, original_name, stored_path, extension, size_bytes, extracted_chars, created_at, extracted_path
                    ) VALUES(
                        :id, :session_id, :original_name, :stored_path, :extension, :size_bytes, :extracted_chars, :created_at, :extracted_path
                    )
                    """,
                    attachment,
                )
                conn.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (self._now_iso(), attachment["session_id"]))
                conn.commit()
        except sqlite3.Error:
            self.logger.exception("Error SQLite al agregar adjunto: session_id=%s", attachment.get("session_id"))
            raise

    def list_attachments(self, session_id: str) -> list[dict]:
        try:
            with self.database.connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM attachments WHERE session_id = ? ORDER BY created_at ASC",
                    (session_id,),
                ).fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error:
            self.logger.exception("Error SQLite listando adjuntos: session_id=%s", session_id)
            return []

    def delete_attachment(self, attachment_id: str) -> None:
        try:
            with self.database.connect() as conn:
                conn.execute("DELETE FROM attachments WHERE id = ?", (attachment_id,))
                conn.commit()
        except sqlite3.Error:
            self.logger.exception("Error SQLite eliminando adjunto: attachment_id=%s", attachment_id)
            raise

    def get_messages(self, session_id: str) -> list[dict]:
        with self.database.connect() as conn:
            rows = conn.execute(
                "SELECT id, role, content, created_at, position FROM messages WHERE session_id = ? ORDER BY position ASC",
                (session_id,),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "role": row["role"],
                "content": row["content"],
                "created_at": row["created_at"],
                "position": row["position"],
            }
            for row in rows
        ]
