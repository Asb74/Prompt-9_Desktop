import re
import unicodedata


SEMANTIC_ALIASES: dict[str, set[str]] = {
    "variedad": {"variedad", "tipo", "producto", "cultivo"},
    "socio": {"socio", "agricultor", "proveedor", "cliente"},
    "neto": {"neto", "kg", "kilos", "peso", "kg netos", "kilogramos", "kgnetos"},
    "importe": {"importe", "total", "euros", "valor", "liquidacion", "liquidación"},
    "precio": {"precio", "€/kg", "precio kg", "precio_kilo", "precio kilo", "eur kg"},
}


def normalize_header(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", " ", text)
    text = text.replace("_", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def detect_semantic_columns(headers: list[str]) -> dict[str, str]:
    normalized_to_original = {normalize_header(h): h for h in headers}
    detected: dict[str, str] = {}
    for semantic_name, aliases in SEMANTIC_ALIASES.items():
        normalized_aliases = {normalize_header(alias) for alias in aliases}
        for normalized_header, original_header in normalized_to_original.items():
            if normalized_header in normalized_aliases:
                detected[semantic_name] = original_header
                break
        if semantic_name in detected:
            continue
        for normalized_header, original_header in normalized_to_original.items():
            if any(alias in normalized_header for alias in normalized_aliases):
                detected[semantic_name] = original_header
                break
    return detected
