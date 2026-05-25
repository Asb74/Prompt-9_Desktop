import logging
from typing import Any

from openai import OpenAI


class OpenAIClient:
    def __init__(self, api_key: str | None = None) -> None:
        self.logger = logging.getLogger(__name__)
        normalized_key = (api_key or "").strip()
        self.api_key = normalized_key
        self.client = OpenAI(api_key=normalized_key) if normalized_key else None

    def is_configured(self) -> bool:
        return bool(self.client)

    def generate_text(self, messages: list[dict[str, Any]], model: str) -> str:
        if not self.client:
            return ""

        try:
            response = self.client.responses.create(
                model=model,
                input=messages,
            )
        except Exception:
            self.logger.exception("Error llamando a OpenAI Responses API")
            raise

        output_text = getattr(response, "output_text", None)
        if isinstance(output_text, str) and output_text.strip():
            return output_text.strip()

        output = getattr(response, "output", []) or []
        chunks: list[str] = []
        for item in output:
            for content in getattr(item, "content", []) or []:
                text_value = getattr(content, "text", None)
                if isinstance(text_value, str) and text_value.strip():
                    chunks.append(text_value.strip())
                    continue

                text_obj = getattr(content, "text", None)
                if text_obj and hasattr(text_obj, "value"):
                    value = getattr(text_obj, "value", "")
                    if isinstance(value, str) and value.strip():
                        chunks.append(value.strip())

        return "\n".join(chunks).strip()
