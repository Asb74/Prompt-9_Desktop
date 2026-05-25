from src.config.settings import OPENAI_API_KEY
from src.services.openai_client import OpenAIClient


class ChatManager:
    FALLBACK_NOT_CONFIGURED = "Respuesta simulada. Configura OPENAI_API_KEY en .env para activar OpenAI."
    FALLBACK_ERROR = "No se pudo obtener respuesta de OpenAI. Revisa la configuración o la conexión."

    def __init__(self, client: OpenAIClient | None = None) -> None:
        self.client = client or OpenAIClient(api_key=OPENAI_API_KEY)
        self.history: list[dict[str, str]] = []

    def send_message(self, user_text: str, model: str) -> str:
        self.history.append({"role": "user", "content": user_text})

        if not self.client.is_configured():
            assistant_text = self.FALLBACK_NOT_CONFIGURED
            self.history.append({"role": "assistant", "content": assistant_text})
            return assistant_text

        try:
            assistant_text = self.client.generate_text(messages=self.history, model=model)
            if not assistant_text:
                assistant_text = self.FALLBACK_ERROR
        except Exception:
            assistant_text = self.FALLBACK_ERROR

        self.history.append({"role": "assistant", "content": assistant_text})
        return assistant_text
