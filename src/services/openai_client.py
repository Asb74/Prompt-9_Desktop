import logging
from typing import Any, Callable, Optional

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
        on_delta: Callable[[str], None],
        should_cancel: Optional[Callable[[], bool]] = None,
    ) -> str:
        if not self.client:
            return ""

        full_text_chunks: list[str] = []
        streamed_chars = 0
        last_fallback_text = ""
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
                        streamed_chars += len(delta)
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
                    # Algunos SDK/eventos alternativos pueden exponer texto acumulado.
                    # En ese caso se envía únicamente el delta nuevo.
                    if fallback_delta.startswith(last_fallback_text):
                        new_chunk = fallback_delta[len(last_fallback_text) :]
                    else:
                        new_chunk = fallback_delta
                    last_fallback_text = fallback_delta
                    if new_chunk:
                        full_text_chunks.append(new_chunk)
                        streamed_chars += len(new_chunk)
                        on_delta(new_chunk)
                    continue

                self.logger.debug("Evento de streaming ignorado: type=%s", event_type)
        except Exception:
            self.logger.exception("Error durante streaming con OpenAI Responses API")
            raise

        result = "".join(full_text_chunks).strip()
        self.logger.info(
            "Streaming completado. Longitud de respuesta=%s chars_recibidos_aprox=%s",
            len(result),
            streamed_chars,
        )
        return result
