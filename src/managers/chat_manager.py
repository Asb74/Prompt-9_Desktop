import logging

from src.config import settings
from src.managers.conversation_manager import ConversationManager
from src.services.openai_client import OpenAIClient


class ChatManager:
    FALLBACK_NOT_CONFIGURED = "Respuesta simulada. Configura OPENAI_API_KEY en .env para activar OpenAI."
    FALLBACK_ERROR = "No se pudo obtener respuesta de OpenAI. Revisa la configuración, el modelo o la conexión."

    def __init__(
        self,
        client: OpenAIClient | None = None,
        conversation_manager: ConversationManager | None = None,
    ) -> None:
        self.logger = logging.getLogger(__name__)
        current = settings.effective_settings()
        self.client = client or OpenAIClient(api_key=current["openai_api_key"])
        self.conversation_manager = conversation_manager or ConversationManager(
            system_prompt=str(current["system_prompt"]),
            max_messages=int(current["max_context_messages"]),
        )

    def update_runtime_settings(self, *, system_prompt: str, max_context_messages: int, api_key: str) -> None:
        self.conversation_manager.system_prompt = system_prompt
        self.conversation_manager.max_messages = max(4, min(100, int(max_context_messages)))
        self.client = OpenAIClient(api_key=api_key)

    def reset_conversation(self) -> None:
        self.conversation_manager.reset()

    def send_message(self, user_text: str, model: str | None) -> str:
        self.conversation_manager.add_user_message(user_text)
        model_name = settings.normalize_model(model)
        self.logger.info("Modelo normalizado para envío: %s", model_name)

        if not self.client.is_configured():
            assistant_text = self.FALLBACK_NOT_CONFIGURED
            self.conversation_manager.add_assistant_message(assistant_text)
            self.logger.info("OpenAI no configurado; se devuelve respuesta simulada.")
            return assistant_text

        try:
            messages = self.conversation_manager.get_messages_for_openai()
            self.logger.info("Enviando %s mensajes a OpenAI con modelo %s", len(messages), model_name)
            assistant_text = self.client.generate_text(messages=messages, model=model_name)
            if not assistant_text:
                self.logger.error("OpenAI devolvió una respuesta vacía.")
                return self.FALLBACK_ERROR

            self.conversation_manager.add_assistant_message(assistant_text)
            return assistant_text
        except Exception:
            self.logger.exception("No se pudo obtener respuesta de OpenAI.")
            return self.FALLBACK_ERROR
