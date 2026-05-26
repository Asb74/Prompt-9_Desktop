import re
import unicodedata
from typing import Any

from src.services.query_intent_detector import QueryIntentDetector


class TabularIntentResolver:
    def __init__(self, detector: QueryIntentDetector | None = None) -> None:
        self.detector = detector or QueryIntentDetector()
        self.pending_clarification: dict[str, Any] | None = None
        self.active_table_context: dict[str, Any] | None = None

    def resolve(self, user_message: str, available_columns: list[str] | None = None) -> dict[str, Any]:
        normalized = self._normalize(user_message)
        columns = available_columns or self._available_columns_from_context()
        if self.pending_clarification:
            resolved = self._resolve_pending(normalized)
            if resolved:
                return {"status": "ready", "intent": resolved}

        direct = self._resolve_direct_patterns(normalized, columns)
        if direct:
            return direct

        detected = self.detector.detect(user_message)
        if detected and detected.get("type") == "table_analysis":
            normalized_intent = self._normalize_detected_intent(detected, columns)
            if normalized_intent.get("status") == "needs_clarification":
                self.pending_clarification = normalized_intent["pending"]
            return normalized_intent

        return {"status": "not_tabular"}

    def update_active_context(self, context: dict[str, Any]) -> None:
        self.active_table_context = context

    def clear_pending(self) -> None:
        self.pending_clarification = None

    def _resolve_pending(self, normalized_message: str) -> dict[str, Any] | None:
        pending = self.pending_clarification or {}
        options = pending.get("options", {})
        for key, column in options.items():
            if key in normalized_message:
                self.pending_clarification = None
                return {
                    "type": "table_analysis",
                    "operation": pending.get("operation", "aggregate_sum"),
                    "group_by": column,
                    "value_column": pending.get("value_column", "Neto"),
                    "group_by_semantic": "crop" if column.lower().startswith("cult") else "variety",
                    "value_semantic": pending.get("value_semantic", "weight_kg"),
                    "top_n": pending.get("top_n"),
                }

        if pending.get("missing_field") == "metric":
            if any(x in normalized_message for x in ("kg", "kilo", "neto", "peso")):
                self.pending_clarification = None
                return {
                    "type": "table_analysis",
                    "operation": "aggregate_sum",
                    "group_by": "Socio",
                    "value_column": pending.get("kg_column", "Neto"),
                    "group_by_semantic": "partner",
                    "value_semantic": "weight_kg",
                    "top_n": 1,
                }
            if any(x in normalized_message for x in ("importe", "euros", "valor")):
                self.pending_clarification = None
                return {
                    "type": "table_analysis",
                    "operation": "aggregate_sum",
                    "group_by": "Socio",
                    "value_column": pending.get("money_column", "Importe"),
                    "group_by_semantic": "partner",
                    "value_semantic": "money_total",
                    "top_n": 1,
                }
            if "entrega" in normalized_message:
                self.pending_clarification = None
                return {
                    "type": "table_analysis",
                    "operation": "count_by",
                    "group_by": "Socio",
                    "group_by_semantic": "partner",
                    "top_n": 1,
                }
        return None

    def _resolve_direct_patterns(self, normalized: str, columns: list[str]) -> dict[str, Any] | None:
        if ("socio" in normalized and "mas" in normalized) or ("socio" in normalized and "más" in normalized):
            if any(x in normalized for x in ("kg", "kilo", "neto", "peso")):
                return {"status": "ready", "intent": self._build_partner_top_weight_intent(columns)}
            if any(x in normalized for x in ("importe", "euros", "valor")):
                money_col = self._find_column(columns, ["importe"]) or "Importe"
                return {"status": "ready", "intent": {
                    "type": "table_analysis", "operation": "aggregate_sum", "group_by": "Socio",
                    "value_column": money_col, "group_by_semantic": "partner", "value_semantic": "money_total", "top_n": 1,
                }}
            if "entrega" in normalized:
                return {"status": "ready", "intent": {"type": "table_analysis", "operation": "count_by", "group_by": "Socio", "group_by_semantic": "partner", "top_n": 1}}
            pending = {
                "operation": "aggregate_sum", "missing_field": "metric", "kg_column": self._find_column(columns, ["neto", "kg"]),
                "money_column": self._find_column(columns, ["importe"]),
            }
            self.pending_clarification = pending
            return {"status": "needs_clarification", "message": "¿Quieres contar entregas, sumar kilos o sumar importe?", "pending": pending}

        if "producto" in normalized and any(x in normalized for x in ("kg", "kilo", "neto", "peso")):
            cultivo = self._find_column(columns, ["cultivo"])
            variedad = self._find_column(columns, ["variedad"])
            if cultivo and variedad:
                pending = {
                    "operation": "aggregate_sum", "value_semantic": "weight_kg", "value_column": self._find_column(columns, ["neto", "kg"]) or "Neto",
                    "missing_field": "group_by", "options": {"cultivo": cultivo, "variedad": variedad},
                }
                self.pending_clarification = pending
                return {
                    "status": "needs_clarification",
                    "message": "Cuando dices “producto”, puedo interpretarlo como Cultivo o como Variedad. ¿Quieres que agrupe por Cultivo o por Variedad?",
                    "pending": {"missing_field": "group_by", "options": [cultivo, variedad]},
                }
            group = variedad or cultivo
            if group:
                return {"status": "ready", "intent": {
                    "type": "table_analysis", "operation": "aggregate_sum", "group_by": group,
                    "value_column": self._find_column(columns, ["neto", "kg"]) or "Neto",
                    "group_by_semantic": "variety" if group == variedad else "crop", "value_semantic": "weight_kg", "top_n": None,
                }}

        return None

    def _normalize_detected_intent(self, intent: dict[str, Any], columns: list[str]) -> dict[str, Any]:
        if self._normalize(str(intent.get("group_by", ""))) == "producto":
            return self._resolve_direct_patterns("kg por producto", columns) or {"status": "not_tabular"}
        return {"status": "ready", "intent": intent}

    def _build_partner_top_weight_intent(self, columns: list[str]) -> dict[str, Any]:
        return {
            "type": "table_analysis",
            "operation": "aggregate_sum",
            "group_by": self._find_column(columns, ["socio"]) or "Socio",
            "value_column": self._find_column(columns, ["neto", "kg"]) or "Neto",
            "group_by_semantic": "partner",
            "value_semantic": "weight_kg",
            "top_n": 1,
        }

    def _available_columns_from_context(self) -> list[str]:
        return list((self.active_table_context or {}).get("available_columns", []) or [])

    def _find_column(self, columns: list[str], keywords: list[str]) -> str | None:
        for col in columns:
            ncol = self._normalize(col)
            if any(k in ncol for k in keywords):
                return col
        return None

    def _normalize(self, text: str) -> str:
        raw = unicodedata.normalize("NFD", (text or "").lower())
        clean = "".join(ch for ch in raw if unicodedata.category(ch) != "Mn")
        return re.sub(r"\s+", " ", clean).strip()
