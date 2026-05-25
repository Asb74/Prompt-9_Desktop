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
        self.logger.info("Conversación creada/reiniciada.")

    def add_user_message(self, content: str) -> None:
        self.messages.append({"role": "user", "content": content})

    def add_assistant_message(self, content: str) -> None:
        self.messages.append({"role": "assistant", "content": content})

    def load_messages(self, messages: list[dict[str, Any]]) -> None:
        valid_roles = {"system", "user", "assistant"}
        rebuilt = [{"role": "system", "content": self.system_prompt}]
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "")
            if role in valid_roles and isinstance(content, str):
                if role == "system":
                    continue
                rebuilt.append({"role": role, "content": content})
        bounded_non_system = rebuilt[1:][-self.max_messages :]
        self.messages = [rebuilt[0], *bounded_non_system]

    def get_messages_for_openai(self) -> list[dict[str, Any]]:
        system_message = self.messages[0]
        non_system_messages = self.messages[1:]
        bounded_non_system = non_system_messages[-self.max_messages :]
        return [system_message, *bounded_non_system]

    def get_all_messages(self) -> list[dict[str, Any]]:
        return list(self.messages)
