import logging
from typing import Any

from src.config.settings import MAX_CONTEXT_MESSAGES, SYSTEM_PROMPT


class ConversationManager:
    def __init__(self, system_prompt: str | None = None, max_messages: int = MAX_CONTEXT_MESSAGES) -> None:
        self.logger = logging.getLogger(__name__)
        self.system_prompt = (system_prompt or SYSTEM_PROMPT).strip()
        self.max_messages = max(1, int(max_messages))
        self.messages: list[dict[str, str]] = []
        self.reset()

    def reset(self) -> None:
        self.messages = [{"role": "system", "content": self.system_prompt}]
        self.logger.info("Conversación reiniciada.")

    def add_user_message(self, content: str) -> None:
        self.messages.append({"role": "user", "content": content})

    def add_assistant_message(self, content: str) -> None:
        self.messages.append({"role": "assistant", "content": content})

    def load_messages(self, messages: list[dict[str, Any]]) -> None:
        self.reset()
        valid_roles = {"system", "user", "assistant"}
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            role = msg.get("role")
            content = msg.get("content")
            if role not in valid_roles or not isinstance(content, str) or not content.strip():
                continue
            if role == "system":
                continue
            self.messages.append({"role": role, "content": content})

        self.messages = [self.messages[0], *self.messages[1:][-self.max_messages :]]
        self.logger.info("Conversación reconstruida con %s mensajes.", len(self.messages) - 1)

    def get_messages_for_openai(self, document_context: str | None = None) -> list[dict[str, Any]]:
        system_message = self.messages[0]
        non_system_messages = self.messages[1:]
        bounded_non_system = non_system_messages[-self.max_messages :]
        if document_context and document_context.strip():
            bounded_non_system = [{"role": "system", "content": document_context.strip()}, *bounded_non_system]
        return [system_message, *bounded_non_system]

    def get_all_messages(self) -> list[dict[str, Any]]:
        return list(self.messages)
