from dotenv import load_dotenv

import logging
import os

from src.config.local_config import load_local_config

load_dotenv()

APP_NAME = "PROM-9™ Desktop"
APP_VERSION = "0.1.0"
DEFAULT_MODEL = "gpt-4.1-mini"
AVAILABLE_MODELS = ["gpt-4.1-mini", "gpt-4o-mini"]
MAX_ATTACHMENT_MB = 20
MAX_DOCUMENT_CHARS = 20000
RECENT_ATTACHMENT_CONTEXT_LIMIT = 3
ALLOWED_EXTENSIONS = {".txt", ".pdf", ".docx", ".xlsx", ".csv"}

MAX_CONTEXT_MESSAGES = 20
STREAMING_ENABLED = True
SYSTEM_PROMPT = "Eres PROM-9™, un asistente de escritorio integrado en una aplicación Python. Responde de forma clara, útil y estructurada. Si falta información, pide los datos necesarios. No inventes datos."


LOCAL_CONFIG = load_local_config(settings_module=__import__(__name__, fromlist=["*"]))


def normalize_model(model: str | None) -> str:
    logger = logging.getLogger(__name__)
    if model is None:
        logger.info("Modelo vacío detectado; usando DEFAULT_MODEL=%s", DEFAULT_MODEL)
        return DEFAULT_MODEL

    normalized = model.strip()
    if not normalized:
        logger.info("Modelo en blanco detectado; usando DEFAULT_MODEL=%s", DEFAULT_MODEL)
        return DEFAULT_MODEL

    if normalized in AVAILABLE_MODELS:
        return normalized

    logger.warning("Modelo inválido '%s'; usando DEFAULT_MODEL=%s", normalized, DEFAULT_MODEL)
    return DEFAULT_MODEL


def resolve_api_key(explicit_key: str | None = None) -> str:
    key = (explicit_key or "").strip()
    if key:
        return key

    env_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if env_key:
        return env_key

    return ""


def effective_settings() -> dict[str, object]:
    default_model = normalize_model(str(LOCAL_CONFIG.get("default_model") or DEFAULT_MODEL))

    system_prompt = str(LOCAL_CONFIG.get("system_prompt") or "").strip() or SYSTEM_PROMPT

    max_context = LOCAL_CONFIG.get("max_context_messages", MAX_CONTEXT_MESSAGES)
    try:
        max_context_int = int(max_context)
    except (TypeError, ValueError):
        max_context_int = MAX_CONTEXT_MESSAGES
    max_context_int = max(4, min(100, max_context_int))

    streaming_enabled = bool(LOCAL_CONFIG.get("streaming_enabled", STREAMING_ENABLED))

    api_key = resolve_api_key()
    logging.getLogger(__name__).info("API key configurada: %s", "sí" if bool(api_key) else "no")

    return {
        "default_model": default_model,
        "system_prompt": system_prompt,
        "max_context_messages": max_context_int,
        "streaming_enabled": streaming_enabled,
        "openai_api_key": api_key,
    }
