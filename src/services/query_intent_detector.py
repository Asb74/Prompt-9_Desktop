import re
from typing import Any


class QueryIntentDetector:
    def detect(self, text: str) -> dict[str, Any] | None:
        normalized = (text or "").lower()
        if not normalized.strip():
            return None

        group_by = self._detect_group_by(normalized)
        metric = self._detect_metric(normalized)
        limit = self._detect_limit(normalized)
        sort = "desc" if any(word in normalized for word in ["top", "mayor", "desc"]) else "asc" if "asc" in normalized else None

        if "total general" in normalized or "total" == normalized.strip():
            return {"operation": "total_general", "group_by": [], "metrics": [metric], "sort": sort, "limit": limit}
        if "count" in normalized or "cuantos" in normalized or "cuántos" in normalized:
            return {"operation": "count", "group_by": group_by, "metrics": [{"column": "*", "aggregation": "count"}], "sort": sort, "limit": limit}
        if metric["aggregation"] == "weighted_average":
            return {"operation": "group_weighted_average" if group_by else "weighted_average", "group_by": group_by, "metrics": [metric], "sort": sort, "limit": limit}
        if group_by:
            return {"operation": f"group_{metric['aggregation']}", "group_by": group_by, "metrics": [metric], "sort": sort, "limit": limit}
        if metric["aggregation"] in {"sum", "avg"}:
            return {"operation": metric["aggregation"], "group_by": [], "metrics": [metric], "sort": sort, "limit": limit}
        return None

    def _detect_group_by(self, text: str) -> list[str]:
        mapping = {"variedad": ["variedad", "producto", "cultivo", "tipo"], "socio": ["socio", "agricultor", "proveedor", "cliente"]}
        groups: list[str] = []
        for canonical, aliases in mapping.items():
            if any(re.search(rf"\b{re.escape(alias)}\b", text) for alias in aliases):
                if "por" in text or "agrup" in text or "resumen" in text or "top" in text:
                    groups.append(canonical)
        return groups

    def _detect_metric(self, text: str) -> dict[str, str]:
        if "precio medio" in text or "media de precios" in text or "precio promedio" in text:
            if "kg" in text or "kilo" in text:
                return {"column": "precio", "aggregation": "weighted_average"}
            return {"column": "precio", "aggregation": "avg"}
        if any(word in text for word in ["importe", "euros", "valor", "liquidacion", "liquidación"]):
            return {"column": "importe", "aggregation": "sum"}
        if any(word in text for word in ["kg", "kilos", "neto", "peso"]):
            return {"column": "neto", "aggregation": "sum"}
        if "media" in text or "promedio" in text:
            return {"column": "neto", "aggregation": "avg"}
        return {"column": "neto", "aggregation": "sum"}

    def _detect_limit(self, text: str) -> int | None:
        match = re.search(r"\btop\s+(\d+)\b", text)
        if match:
            return int(match.group(1))
        return None
