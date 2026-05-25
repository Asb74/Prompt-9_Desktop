import logging
from datetime import datetime
from pathlib import Path


class ExportService:
    """Servicio de exportación de sesiones a texto plano o Markdown."""

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)

    def export_session_to_txt(self, session: dict, output_path: str) -> bool:
        return self._export_session(session, output_path, markdown=False)

    def export_session_to_markdown(self, session: dict, output_path: str) -> bool:
        return self._export_session(session, output_path, markdown=True)

    def _export_session(self, session: dict, output_path: str, markdown: bool) -> bool:
        try:
            content = self._build_export_content(session, markdown=markdown)
            Path(output_path).write_text(content, encoding="utf-8")
            return True
        except Exception:
            self.logger.exception("Error escribiendo exportación en %s", output_path)
            return False

    def _build_export_content(self, session: dict, markdown: bool = False) -> str:
        title = session.get("title", "Nueva sesión")
        created_at = self._format_datetime(session.get("created_at"))
        updated_at = self._format_datetime(session.get("updated_at"))
        model = session.get("model", "-")

        if markdown:
            lines = [
                f"# {title}",
                "",
                f"- **Creada:** {created_at}",
                f"- **Actualizada:** {updated_at}",
                f"- **Modelo:** {model}",
                "",
                "---",
                "",
            ]
        else:
            lines = [
                f"Sesión: {title}",
                f"Creada: {created_at}",
                f"Actualizada: {updated_at}",
                f"Modelo: {model}",
                "",
                "=" * 60,
                "",
            ]

        for msg in session.get("messages", []):
            role = str(msg.get("role", "system")).upper()
            timestamp = self._format_datetime(msg.get("created_at"))
            content = str(msg.get("content", "")).rstrip()

            if markdown:
                lines.extend([f"## [{timestamp}] {role}", "", content, ""])
            else:
                lines.extend([f"[{timestamp}] {role}", content, ""])

        return "\n".join(lines).rstrip() + "\n"

    @staticmethod
    def _format_datetime(value: str | None) -> str:
        if not value:
            return "-"
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            return value
