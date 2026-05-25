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
        normalized_model = normalize_model(model)
        session = {
            "id": str(uuid4()),
            "title": title,
            "created_at": now,
            "updated_at": now,
            "model": normalized_model,
            "messages": [],
        }
        self.logger.info("Sesión creada: %s", session["id"])
        return session

    def list_sessions(self) -> list[dict]:
        sessions: list[dict] = []
        for json_path in sorted(self.sessions_dir.glob("*.json")):
            try:
                with json_path.open("r", encoding="utf-8") as fh:
                    data = json.load(fh)
                if isinstance(data, dict) and data.get("id"):
                    model_before = data.get("model")
                    normalized_model = normalize_model(model_before)
                    if model_before != normalized_model:
                        data["model"] = normalized_model
                        self.save_session(data)
                    sessions.append(data)
                    self.logger.info("Sesión cargada: %s", data.get("id"))
            except Exception:
                self.logger.exception("Error leyendo JSON de sesión: %s", json_path)
        sessions.sort(key=lambda s: s.get("updated_at", ""), reverse=True)
        return sessions

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
