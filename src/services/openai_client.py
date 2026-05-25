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

    def stream_text(
        self,
        messages: list[dict[str, Any]],
        model: str,
        on_delta: callable,
        should_cancel: callable | None = None,
    ) -> str:
        if not self.client:
            return ""

        full_text_chunks: list[str] = []
        self.logger.info("Inicio de streaming OpenAI: model=%s mensajes=%s", model, len(messages))
        try:
            stream = self.client.responses.create(model=model, input=messages, stream=True)
            for event in stream:
                if callable(should_cancel) and should_cancel():
                    self.logger.info("Streaming cancelado por el usuario.")
                    break

                event_type = getattr(event, "type", "")
                if event_type == "response.output_text.delta":
                    delta = getattr(event, "delta", "")
                    if isinstance(delta, str) and delta:
                        full_text_chunks.append(delta)
                        on_delta(delta)
                    continue

                if event_type == "response.error":
                    self.logger.error("Evento de error recibido en streaming: %s", event)
                    break

                if event_type == "response.completed":
                    self.logger.info("Evento de streaming completado recibido.")
                    break

                # Compatibilidad defensiva ante cambios de SDK/eventos.
                fallback_delta = getattr(event, "delta", None)
                if isinstance(fallback_delta, str) and fallback_delta:
                    full_text_chunks.append(fallback_delta)
                    on_delta(fallback_delta)
        except Exception:
            self.logger.exception("Error durante streaming con OpenAI Responses API")
            raise

        result = "".join(full_text_chunks).strip()
        self.logger.info("Streaming completado. Longitud de respuesta=%s", len(result))
        return result
