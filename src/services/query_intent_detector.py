import re
import unicodedata
from typing import Any


class QueryIntentDetector:
    def detect(self, text: str) -> dict[str, Any] | None:
        normalized = self._normalize(text)
        if not normalized:
            return None

        if "top" in normalized and "socios" in normalized and ("kg" in normalized or "kilos" in normalized):
            top = self._detect_top_n(normalized)
            return {
                "type": "table_analysis",
                "operation": "aggregate_sum",
                "group_by": "Socio",
                "value_column": "Neto",
                "group_by_semantic": "partner",
                "value_semantic": "weight_kg",
                "top_n": top,
            }

        if "precio medio por kg" in normalized:
            group_by = "Variedad" if "variedad" in normalized else "Socio" if "socio" in normalized else "Variedad"
            return {
                "type": "table_analysis",
                "operation": "weighted_average",
                "group_by": group_by,
                "numerator_column": "Importe",
                "denominator_column": "Neto",
                "group_by_semantic": "variety" if group_by == "Variedad" else "partner",
                "numerator_semantic": "money_total",
                "denominator_semantic": "weight_kg",
            }

        if "precio medio por variedad" in normalized:
            return {
                "type": "table_analysis",
                "operation": "average",
                "group_by": "Variedad",
                "value_column": "Precio",
            }


        if any(x in normalized for x in ["kg por producto", "kilos por producto", "neto por producto", "kg por cultivo", "kilos por cultivo", "neto por cultivo", "kg por variedad", "kilos por variedad", "kg entregados por variedad", "neto por variedad"]):
            if any(x in normalized for x in ["kg por producto", "kilos por producto", "neto por producto"]):
                return {
                    "type": "table_analysis",
                    "operation": "aggregate_sum",
                    "group_by": "Producto",
                    "value_column": "Neto",
                    "group_by_semantic": "product",
                    "value_semantic": "weight_kg",
                }
            return {"type": "table_analysis", "operation": "aggregate_sum", "group_by": "Variedad", "value_column": "Neto", "group_by_semantic": "variety", "value_semantic": "weight_kg"}

        if "neto por socio" in normalized:
            return {"type": "table_analysis", "operation": "aggregate_sum", "group_by": "Socio", "value_column": "Neto", "group_by_semantic": "partner", "value_semantic": "weight_kg"}

        if "importe por socio" in normalized:
            return {"type": "table_analysis", "operation": "aggregate_sum", "group_by": "Socio", "value_column": "Importe", "group_by_semantic": "partner", "value_semantic": "money_total"}

        if "total neto" in normalized:
            return {"type": "table_analysis", "operation": "total_sum", "value_column": "Neto", "value_semantic": "weight_kg"}

        if "total importe" in normalized:
            return {"type": "table_analysis", "operation": "total_sum", "value_column": "Importe", "value_semantic": "money_total"}

        return None

    def _detect_top_n(self, text: str) -> int:
        match = re.search(r"top\s+(\d+)", text)
        return int(match.group(1)) if match else 10

    def _normalize(self, text: str) -> str:
        raw = unicodedata.normalize("NFD", (text or "").lower())
        clean = "".join(ch for ch in raw if unicodedata.category(ch) != "Mn")
        return " ".join(clean.split())
