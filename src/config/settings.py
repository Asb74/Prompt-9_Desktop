from dotenv import load_dotenv

import os

load_dotenv()

APP_NAME = "PROM-9™ Desktop"
APP_VERSION = "0.1.0"
DEFAULT_MODEL = "gpt-4.1-mini"
AVAILABLE_MODELS = ["gpt-4.1-mini", "gpt-4o-mini"]
MAX_ATTACHMENT_MB = 20
ALLOWED_EXTENSIONS = {".txt", ".pdf", ".docx", ".xlsx", ".csv", ".png", ".jpg", ".jpeg"}
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

MAX_CONTEXT_MESSAGES = 20
SYSTEM_PROMPT = "Eres PROM-9™, un asistente de escritorio integrado en una aplicación Python. Responde de forma clara, útil y estructurada. Si falta información, pide los datos necesarios. No inventes datos."


def normalize_model(model: str | None) -> str:
    if model is None:
        return DEFAULT_MODEL

    normalized = model.strip()
    if not normalized:
        return DEFAULT_MODEL

    if normalized in AVAILABLE_MODELS:
        return normalized

    return DEFAULT_MODEL
