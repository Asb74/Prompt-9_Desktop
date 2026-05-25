import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from src.config import settings
from src.database.session_repository import SessionRepository
from src.services.document_loader import DocumentLoader
from src.services.text_chunker import truncate_text
from src.utils.paths import attachments_dir


class AttachmentManager:
    def __init__(self, session_repository: SessionRepository, document_loader: DocumentLoader | None = None) -> None:
        self.logger = logging.getLogger(__name__)
        self.session_repository = session_repository
        self.document_loader = document_loader or DocumentLoader()

    def add_attachment(self, session_id: str, source_path: str) -> dict:
        source = Path(source_path)
        if not source.exists() or not source.is_file():
            raise ValueError("El archivo no existe o no es válido.")

        extension = source.suffix.lower()
        if extension not in settings.ALLOWED_EXTENSIONS:
            raise ValueError(f"Extensión no permitida: {extension}")

        size_bytes = source.stat().st_size
        max_bytes = int(settings.MAX_ATTACHMENT_MB) * 1024 * 1024
        if size_bytes > max_bytes:
            raise ValueError(f"Archivo excede el máximo permitido de {settings.MAX_ATTACHMENT_MB} MB")

        attachment_id = str(uuid4())
        safe_name = "".join(c if c.isalnum() or c in {"-", "_", "."} else "_" for c in source.name)
        session_dir = attachments_dir() / session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        stored_name = f"{attachment_id}_{safe_name}"
        stored_path = session_dir / stored_name
        if stored_path.exists():
            raise ValueError("Conflicto de nombre de archivo de adjunto.")

        shutil.copy2(source, stored_path)

        extracted_text = self.document_loader.extract_text(str(stored_path))
        limited_text, was_truncated = truncate_text(extracted_text, int(settings.MAX_DOCUMENT_CHARS))

        extracted_path = session_dir / f"{attachment_id}_extracted.txt"
        extracted_path.write_text(limited_text, encoding="utf-8")

        created_at = datetime.now(timezone.utc).isoformat()
        payload = {
            "id": attachment_id,
            "session_id": session_id,
            "message_id": None,
            "original_name": source.name,
            "stored_path": str(stored_path),
            "extension": extension,
            "size_bytes": size_bytes,
            "extracted_chars": len(limited_text),
            "created_at": created_at,
            "extracted_path": str(extracted_path),
            "extracted_text_path": str(extracted_path),
        }
        self.session_repository.add_attachment(payload)
        self.logger.info(
            "Adjunto agregado como pendiente: session_id=%s attachment_id=%s archivo=%s tipo=%s bytes=%s chars=%s truncado=%s",
            session_id,
            attachment_id,
            source.name,
            extension,
            size_bytes,
            len(limited_text),
            was_truncated,
        )
        payload["extracted_preview"] = limited_text[:500]
        return payload

    def list_attachments(self, session_id: str) -> list[dict]:
        attachments = self.session_repository.list_attachments(session_id)
        hydrated: list[dict] = []
        for att in attachments:
            hydrated.append(self._hydrate_attachment_text(session_id, att))
        return hydrated

    def list_pending_attachments(self, session_id: str) -> list[dict]:
        attachments = self.session_repository.list_pending_attachments(session_id)
        hydrated: list[dict] = []
        for att in attachments:
            hydrated.append(self._hydrate_attachment_text(session_id, att))
        return hydrated

    def list_recent_message_attachments(self, session_id: str, limit: int = 3) -> list[dict]:
        attachments = self.session_repository.list_recent_message_attachments(session_id=session_id, limit=limit)
        hydrated: list[dict] = []
        for att in attachments:
            hydrated.append(self._hydrate_attachment_text(session_id, att))
        return hydrated

    def attach_pending_files_to_message(self, session_id: str, message_id: str, attachment_ids: list[str]) -> None:
        self.session_repository.attach_pending_files_to_message(session_id, message_id, attachment_ids)
        self.logger.info(
            "Adjuntos vinculados a mensaje: session_id=%s message_id=%s total=%s",
            session_id,
            message_id,
            len(attachment_ids),
        )

    def _hydrate_attachment_text(self, session_id: str, attachment: dict) -> dict:
        enriched = dict(attachment)
        extracted_text = ""
        extracted_path = enriched.get("extracted_path")
        enriched["extracted_text_path"] = extracted_path

        if extracted_path:
            extracted_file = Path(extracted_path)
            if extracted_file.exists():
                extracted_text = extracted_file.read_text(encoding="utf-8", errors="replace")

        if not extracted_text:
            stored_path = enriched.get("stored_path")
            if stored_path and Path(stored_path).exists():
                try:
                    raw_text = self.document_loader.extract_text(str(stored_path))
                    extracted_text, was_truncated = truncate_text(raw_text, int(settings.MAX_DOCUMENT_CHARS))
                    if extracted_text:
                        session_dir = attachments_dir() / session_id
                        session_dir.mkdir(parents=True, exist_ok=True)
                        extracted_file = session_dir / f"{enriched.get('id', uuid4())}_extracted.txt"
                        extracted_file.write_text(extracted_text, encoding="utf-8")
                        enriched["extracted_path"] = str(extracted_file)
                        enriched["extracted_text_path"] = str(extracted_file)
                        self.logger.info(
                            "Texto extraído regenerado para adjunto id=%s chars=%s truncado=%s",
                            enriched.get("id"),
                            len(extracted_text),
                            was_truncated,
                        )
                except Exception:
                    self.logger.exception("No se pudo regenerar texto extraído para adjunto id=%s", enriched.get("id"))

        enriched["extracted_text"] = extracted_text
        return enriched

    def remove_attachment(self, attachment_id: str) -> None:
        self.session_repository.delete_attachment(attachment_id)
