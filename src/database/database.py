import logging
import sqlite3
from pathlib import Path

from src.utils.paths import data_dir


class Database:
    def __init__(self, db_path: Path | None = None) -> None:
        self.logger = logging.getLogger(__name__)
        base_data_dir = data_dir()
        self.db_path = (db_path or base_data_dir / "prom9.db").resolve()

    def connect(self) -> sqlite3.Connection:
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            self.logger.info("Base SQLite inicializada: %s", self.db_path)
            return conn
        except sqlite3.Error:
            self.logger.exception("Error SQLite al abrir conexión: %s", self.db_path)
            raise

    def initialize(self) -> None:
        schema = [
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                model TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                position INTEGER NOT NULL,
                FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS attachments (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                original_name TEXT NOT NULL,
                stored_path TEXT NOT NULL,
                extension TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                extracted_chars INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                extracted_path TEXT,
                FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_sessions_title ON sessions(title)",
            "CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id)",
            "CREATE INDEX IF NOT EXISTS idx_messages_session_content ON messages(session_id, content)",
            "CREATE INDEX IF NOT EXISTS idx_sessions_updated_at ON sessions(updated_at)",
            "CREATE INDEX IF NOT EXISTS idx_attachments_session_id ON attachments(session_id)",
        ]
        try:
            with self.connect() as conn:
                for statement in schema:
                    conn.execute(statement)
                conn.commit()
            self.logger.info("Tablas e índices SQLite creados/verificados.")
        except sqlite3.Error:
            self.logger.exception("Error SQLite al crear/verificar esquema.")
            raise
