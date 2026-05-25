import copy
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path


class ConversationExporter:
    ROLE_DISPLAY = {"user": "Tú", "assistant": "PROM-9", "system": "Sistema"}
    INVALID_FILENAME_CHARS_RE = re.compile(r'[\\/:*?"<>|]+')
    MULTISPACE_RE = re.compile(r"\s+")

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)

    def export_txt(self, session: dict, output_path: str) -> None:
        Path(output_path).write_text(self._build_txt_content(session), encoding="utf-8")

    def export_markdown(self, session: dict, output_path: str) -> None:
        Path(output_path).write_text(self._build_markdown_content(session), encoding="utf-8")

    def export_json(self, session: dict, output_path: str) -> None:
        payload = {
            "app": "PROM-9™ Desktop",
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "session": self._clean_session_for_export(session),
        }
        Path(output_path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def build_safe_filename(self, title: str, extension: str) -> str:
        ext = extension.lower().lstrip(".")
        safe_ext = ext if ext in {"txt", "md", "json"} else "txt"
        date_part = datetime.now().strftime("%Y%m%d")

        base_title = title.strip() if title else "Sesion"
        base_title = self.INVALID_FILENAME_CHARS_RE.sub("", base_title)
        base_title = self.MULTISPACE_RE.sub("_", base_title)
        base_title = re.sub(r"_+", "_", base_title).strip("._")
        if not base_title:
            base_title = "Sesion"

        max_title_len = 80
        base_title = base_title[:max_title_len]
        return f"{date_part}_{base_title}.{safe_ext}"

    def _build_txt_content(self, session: dict) -> str:
        lines = [
            "PROM-9™ Desktop",
            f"Sesión: {session.get('title', 'Nueva sesión')}",
            f"Fecha creación: {self._format_datetime(session.get('created_at'))}",
            f"Última actualización: {self._format_datetime(session.get('updated_at'))}",
            f"Modelo: {session.get('model', '-')}",
            "",
            "-" * 40,
            "",
        ]

        for message in self._iter_valid_messages(session):
            label = self.ROLE_DISPLAY.get(message.get("role", "system"), "Sistema")
            lines.extend(
                [
                    f"[{self._format_datetime(message.get('created_at'))}] {label}:",
                    str(message.get("content", "")),
                ]
            )
            self._append_attachments_lines(lines, message.get("attachments", []), markdown=False)
            lines.append("")

        return "\n".join(lines).rstrip() + "\n"

    def _build_markdown_content(self, session: dict) -> str:
        lines = [
            "# PROM-9™ Desktop",
            "",
            "## Sesión",
            f"- **Título:** {session.get('title', 'Nueva sesión')}",
            f"- **Creada:** {self._format_datetime(session.get('created_at'))}",
            f"- **Actualizada:** {self._format_datetime(session.get('updated_at'))}",
            f"- **Modelo:** {session.get('model', '-')}",
            "",
            "---",
            "",
            "## Conversación",
            "",
        ]

        for message in self._iter_valid_messages(session):
            label = self.ROLE_DISPLAY.get(message.get("role", "system"), "Sistema")
            lines.extend(
                [
                    f"### {label} — {self._format_datetime(message.get('created_at'))}",
                    str(message.get("content", "")),
                ]
            )
            self._append_attachments_lines(lines, message.get("attachments", []), markdown=True)
            lines.append("")

        return "\n".join(lines).rstrip() + "\n"

    def _iter_valid_messages(self, session: dict) -> list[dict]:
        valid_messages: list[dict] = []
        for message in session.get("messages", []):
            if not isinstance(message, dict):
                continue
            content = message.get("content")
            if not isinstance(content, str) or not content.strip():
                continue
            valid_messages.append(message)
        return valid_messages

    def _clean_session_for_export(self, session: dict) -> dict:
        clean = copy.deepcopy(session)
        if isinstance(clean, dict):
            clean.pop("api_key", None)
            messages = clean.get("messages", [])
            if isinstance(messages, list):
                for message in messages:
                    attachments = message.get("attachments", []) if isinstance(message, dict) else []
                    if isinstance(attachments, list):
                        message["attachments"] = [
                            {
                                "id": att.get("id"),
                                "original_name": att.get("original_name"),
                                "extension": att.get("extension"),
                                "size_bytes": att.get("size_bytes"),
                            }
                            for att in attachments
                            if isinstance(att, dict)
                        ]
        return clean

    @staticmethod
    def _append_attachments_lines(lines: list[str], attachments: list[dict], markdown: bool) -> None:
        if not attachments:
            return
        lines.append("Adjuntos:")
        for attachment in attachments:
            name = attachment.get("original_name", "archivo")
            lines.append(f"- {name}")

    @staticmethod
    def _format_datetime(value: str | None) -> str:
        if not value:
            return "-"
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            return value
