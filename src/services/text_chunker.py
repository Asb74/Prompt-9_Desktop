from pathlib import Path

from src.config import settings


def truncate_text(text: str, max_chars: int) -> tuple[str, bool]:
    normalized = (text or "").strip()
    if len(normalized) <= max_chars:
        return normalized, False
    return normalized[:max_chars].rstrip(), True


def build_document_context(attachments: list[dict]) -> str:
    blocks: list[str] = []
    max_chars = int(settings.MAX_DOCUMENT_CHARS)
    for att in attachments:
        extracted_path = att.get("extracted_path")
        if not extracted_path:
            continue

        path = Path(extracted_path)
        if not path.exists():
            continue

        content = path.read_text(encoding="utf-8", errors="replace")
        truncated_content, truncated = truncate_text(content, max_chars)
        name = att.get("original_name", "archivo")
        block = [f"[Documento adjunto: {name}]", "Contenido extraído:", truncated_content or "(Sin contenido textual extraíble)"]
        if truncated:
            block.append("[Contenido truncado por límite de seguridad]")
        blocks.append("\n".join(block))

    if not blocks:
        return ""

    return "Contexto documental disponible para esta sesión:\n\n" + "\n\n".join(blocks)
