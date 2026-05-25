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
        allowed = {".txt", ".csv", ".pdf", ".docx", ".xlsx"}
        if extension not in allowed:
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
            "original_name": source.name,
            "stored_path": str(stored_path),
            "extension": extension,
            "size_bytes": size_bytes,
            "extracted_chars": len(limited_text),
            "created_at": created_at,
            "extracted_path": str(extracted_path),
        }
        self.session_repository.add_attachment(payload)
        self.logger.info(
            "Adjunto agregado: session_id=%s archivo=%s tipo=%s bytes=%s chars=%s truncado=%s",
            session_id,
            source.name,
            extension,
            size_bytes,
            len(limited_text),
            was_truncated,
        )
        payload["extracted_preview"] = limited_text[:500]
        return payload

    def list_attachments(self, session_id: str) -> list[dict]:
        return self.session_repository.list_attachments(session_id)

    def remove_attachment(self, attachment_id: str) -> None:
        self.session_repository.delete_attachment(attachment_id)
