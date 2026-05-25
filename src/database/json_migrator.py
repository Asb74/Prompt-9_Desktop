import json
import logging
from pathlib import Path

from src.config import settings
from src.database.session_repository import SessionRepository
from src.utils.paths import data_dir


class JsonMigrator:
    def __init__(self, repository: SessionRepository, sessions_dir: Path | None = None) -> None:
        self.logger = logging.getLogger(__name__)
        self.repository = repository
        base_data = data_dir()
        self.sessions_dir = sessions_dir or (base_data / "sessions")
        self.marker_path = base_data / ".json_migrated"

    def migrate(self) -> int:
        self.logger.info("Migración JSON->SQLite iniciada.")
        migrated_count = 0
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        for json_path in self.sessions_dir.glob("*.json"):
            try:
                with json_path.open("r", encoding="utf-8") as fh:
                    data = json.load(fh)
            except Exception:
                self.logger.exception("JSON corrupto ignorado: %s", json_path)
                continue

            if not isinstance(data, dict) or not data.get("id"):
                self.logger.error("JSON inválido ignorado: %s", json_path)
                continue

            session_id = str(data.get("id"))
            if self.repository.get_session(session_id):
                continue

            session_payload = {
                "id": session_id,
                "title": data.get("title") or "Nueva sesión",
                "created_at": data.get("created_at"),
                "updated_at": data.get("updated_at"),
                "model": settings.normalize_model(data.get("model")),
                "messages": data.get("messages") or [],
            }
            self.repository.save_session(session_payload)
            migrated_count += 1
            self.logger.info("Sesión migrada desde JSON: %s", session_id)

        self.marker_path.write_text("ok\n", encoding="utf-8")
        self.logger.info("Migración JSON->SQLite finalizada. Sesiones migradas: %s", migrated_count)
        return migrated_count
