import json
import logging
from pathlib import Path
from typing import Any

from src.utils.paths import project_root

logger = logging.getLogger(__name__)
CONFIG_FILENAME = "config.local.json"


def _config_path() -> Path:
    return project_root() / CONFIG_FILENAME


def default_config(settings_module: Any) -> dict[str, Any]:
    return {
        "default_model": settings_module.DEFAULT_MODEL,
        "system_prompt": settings_module.SYSTEM_PROMPT,
        "max_context_messages": settings_module.MAX_CONTEXT_MESSAGES,
        "streaming_enabled": settings_module.STREAMING_ENABLED,
    }


def load_local_config(settings_module: Any) -> dict[str, Any]:
    defaults = default_config(settings_module)
    path = _config_path()
    if not path.exists():
        logger.info("config.local.json no existe; usando configuración por defecto.")
        return defaults

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("Configuración corrupta o no legible; usando configuración por defecto.")
        return defaults

    if not isinstance(data, dict):
        logger.error("config.local.json no tiene formato objeto; usando defaults.")
        return defaults

    merged = dict(defaults)
    for key in ("default_model", "system_prompt", "max_context_messages", "streaming_enabled"):
        if key in data:
            merged[key] = data[key]
    logger.info("Configuración local cargada desde %s", path)
    return merged


def save_local_config(config: dict[str, Any]) -> None:
    payload = {
        "default_model": config.get("default_model", ""),
        "system_prompt": config.get("system_prompt", ""),
        "max_context_messages": config.get("max_context_messages", 20),
        "streaming_enabled": bool(config.get("streaming_enabled", True)),
    }
    try:
        path = _config_path()
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("Configuración local guardada en %s", path)
    except Exception:
        logger.exception("Error al guardar configuración local")
