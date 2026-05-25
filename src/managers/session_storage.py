import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from src.config.settings import normalize_model


class SessionStorage:
    def __init__(self, base_dir: Path | None = None) -> None:
        self.logger = logging.getLogger(__name__)
        root = Path(__file__).resolve().parents[2]
        self.sessions_dir = (base_dir or root / "data" / "sessions").resolve()
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def create_session(self, model: str | None, title: str = "Nueva sesión") -> dict:
        now = self._now_iso()
        session = {
            "id": str(uuid4()),
            "title": title,
            "created_at": now,
            "updated_at": now,
            "model": normalize_model(model),
            "messages": [],
        }
        self.logger.info("Sesión creada: %s", session["id"])
        return session

    def list_sessions(self) -> list[dict]:
        sessions: list[dict] = []
        for json_path in self.sessions_dir.glob("*.json"):
            session = self._load_json_file(json_path)
            if session:
                sessions.append(session)
        sessions.sort(key=lambda s: s.get("updated_at", ""), reverse=True)
        self.logger.info("Sesiones cargadas: %s", len(sessions))
        return sessions

    def load_session(self, session_id: str) -> dict | None:
        return self._load_json_file(self.sessions_dir / f"{session_id}.json")

    def save_session(self, session: dict) -> None:
        try:
            session["updated_at"] = self._now_iso()
            session["model"] = normalize_model(session.get("model"))
            output_path = self.sessions_dir / f"{session['id']}.json"
            with output_path.open("w", encoding="utf-8") as fh:
                json.dump(session, fh, ensure_ascii=False, indent=2)
            self.logger.info("Sesión guardada: %s", session["id"])
        except Exception:
            self.logger.exception("Error guardando JSON de sesión: %s", session.get("id"))

    def delete_session(self, session_id: str) -> bool:
        json_path = self.sessions_dir / f"{session_id}.json"
        if not json_path.exists():
            return False
        json_path.unlink()
        self.logger.info("Sesión eliminada: %s", session_id)
        return True

    def rename_session(self, session_id: str, new_title: str) -> dict | None:
        session = self.load_session(session_id)
        if not session:
            return None
        cleaned_title = (new_title or "").strip()
        if not cleaned_title:
            return session
        session["title"] = cleaned_title
        self.save_session(session)
        self.logger.info("Sesión renombrada: %s", session_id)
        return session

    def update_session_title_from_first_user_message(self, session: dict) -> dict:
        if session.get("title") != "Nueva sesión":
            return session
        for msg in session.get("messages", []):
            if msg.get("role") == "user":
                content = (msg.get("content") or "").strip()
                if content:
                    session["title"] = content[:40]
                break
        return session

    def _load_json_file(self, json_path: Path) -> dict | None:
        try:
            with json_path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            self.logger.exception("JSON corrupto ignorado: %s", json_path)
            return None

        if not isinstance(data, dict) or not data.get("id"):
            self.logger.error("JSON inválido ignorado: %s", json_path)
            return None

        data.setdefault("title", "Nueva sesión")
        data.setdefault("created_at", self._now_iso())
        data.setdefault("updated_at", self._now_iso())
        data.setdefault("messages", [])
        data["model"] = normalize_model(data.get("model"))
        return data
