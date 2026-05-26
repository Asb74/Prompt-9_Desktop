import logging
import re
import unicodedata
from datetime import datetime
from itertools import combinations
from typing import Any

SEMANTIC_TYPES = [
    "weight_kg",
    "money_total",
    "price_per_kg",
    "variety",
    "partner",
    "date",
    "category",
]

SEMANTIC_SYNONYMS: dict[str, list[str]] = {
    "weight_kg": ["neto", "kg", "kilos", "peso", "peso neto", "kg netos"],
    "money_total": ["importe", "total", "euros", "eur", "liquidacion", "valor", "importe total"],
    "price_per_kg": ["precio", "precio kg", "precio kilo", "p kilo", "eur kg", "euro kg", "kg precio"],
    "variety": ["variedad", "producto", "cultivo", "tipo variedad", "clase"],
    "partner": ["socio", "agricultor", "proveedor", "cliente", "productor", "codigo socio"],
    "date": ["fecha", "dia", "date"],
    "category": ["categoria", "calibre", "grupo", "tipo"],
}


class SemanticColumnInference:
    def __init__(self, confidence_threshold: float = 0.60, relationship_tolerance: float = 0.05) -> None:
        self.logger = logging.getLogger(__name__)
        self.confidence_threshold = confidence_threshold
        self.relationship_tolerance = relationship_tolerance

    def normalize_text(self, text: str) -> str:
        raw = unicodedata.normalize("NFD", str(text or "").lower())
        clean = "".join(ch for ch in raw if unicodedata.category(ch) != "Mn")
        clean = clean.replace("€/", " eur ").replace("€", " eur ")
        clean = re.sub(r"[^a-z0-9\s._/-]", " ", clean)
        clean = clean.replace(".", " ").replace("_", " ").replace("-", " ").replace("/", " ")
        return " ".join(clean.split())

    def profile_column(self, rows: list[dict], column_name: str) -> dict:
        values = [row.get(column_name) for row in rows]
        non_empty = [v for v in values if str(v or "").strip()]
        numeric_values = [self._to_float(v) for v in non_empty]
        numeric = [v for v in numeric_values if v is not None]
        date_like = [v for v in non_empty if self._looks_date_like(v)]
        text_count = sum(1 for v in non_empty if self._to_float(v) is None)
        return {
            "total_values": len(values),
            "non_empty_count": len(non_empty),
            "numeric_count": len(numeric),
            "text_count": text_count,
            "date_like_count": len(date_like),
            "unique_count": len({str(v).strip() for v in non_empty}),
            "sample_values": [str(v) for v in non_empty[:6]],
            "min_numeric": min(numeric) if numeric else None,
            "max_numeric": max(numeric) if numeric else None,
            "avg_numeric": (sum(numeric) / len(numeric)) if numeric else None,
        }

    def score_by_name(self, normalized_header: str, semantic_type: str) -> float:
        synonyms = [self.normalize_text(s) for s in SEMANTIC_SYNONYMS.get(semantic_type, [])]
        if normalized_header in synonyms:
            return 0.95
        if any(s in normalized_header for s in synonyms):
            return 0.80
        tokens = set(normalized_header.split())
        overlap = max((len(tokens.intersection(set(s.split()))) / max(1, len(set(s.split())))) for s in synonyms) if synonyms else 0
        return min(0.70, overlap * 0.70)

    def score_by_profile(self, profile: dict, semantic_type: str) -> float:
        non_empty = max(1, profile["non_empty_count"])
        numeric_ratio = profile["numeric_count"] / non_empty
        date_ratio = profile["date_like_count"] / non_empty
        unique_ratio = profile["unique_count"] / non_empty
        avg_num = profile.get("avg_numeric")

        if semantic_type in {"weight_kg", "money_total", "price_per_kg"}:
            base = numeric_ratio * 0.8
            if semantic_type == "price_per_kg" and avg_num is not None and 0 < avg_num < 100:
                base += 0.15
            if semantic_type == "weight_kg" and avg_num is not None and avg_num >= 10:
                base += 0.10
            if semantic_type == "money_total" and avg_num is not None and avg_num >= 20:
                base += 0.12
            return min(1.0, base)
        if semantic_type == "date":
            return min(1.0, max(date_ratio, (1 - numeric_ratio) * 0.3))
        if semantic_type in {"variety", "partner", "category"}:
            text_ratio = profile["text_count"] / non_empty
            repetition = 1 - unique_ratio
            return min(1.0, (text_ratio * 0.65) + (repetition * 0.35))
        return 0.0

    def detect_numeric_relationships(self, rows: list[dict], candidate_columns: list[str]) -> list[dict]:
        rels: list[dict] = []
        if len(candidate_columns) < 3:
            return rels
        for weight_col, money_col, price_col in combinations(candidate_columns, 3):
            matches = 0
            checked = 0
            for row in rows:
                w, m, p = self._to_float(row.get(weight_col)), self._to_float(row.get(money_col)), self._to_float(row.get(price_col))
                if w is None or m is None or p is None or m == 0:
                    continue
                checked += 1
                if abs(m - (w * p)) / abs(m) <= self.relationship_tolerance:
                    matches += 1
            if checked >= 5 and (matches / checked) >= 0.60:
                rels.append({"weight": weight_col, "money": money_col, "price": price_col, "match_ratio": round(matches / checked, 3), "rows_checked": checked})
        return rels

    def infer_schema(self, tables: list[dict]) -> dict:
        results = {"tables": []}
        for table in tables:
            rows = table.get("rows", [])
            headers = table.get("headers", [])
            columns: dict[str, dict[str, Any]] = {}
            candidate_numeric: list[str] = []
            for header in headers:
                norm = self.normalize_text(header)
                profile = self.profile_column(rows, header)
                if profile["numeric_count"] > 0:
                    candidate_numeric.append(header)
                best_type = "unknown"
                best_score = 0.0
                reason = "sin evidencia suficiente"
                for stype in SEMANTIC_TYPES:
                    name_score = self.score_by_name(norm, stype)
                    profile_score = self.score_by_profile(profile, stype)
                    total = (name_score * 0.65) + (profile_score * 0.35)
                    if total > best_score:
                        best_score = total
                        best_type = stype
                        reason = f"nombre={name_score:.2f}, perfil={profile_score:.2f}"
                columns[header] = {"semantic_type": best_type if best_score >= 0.35 else "unknown", "confidence": round(best_score, 3), "reason": reason}

            relationships = self.detect_numeric_relationships(rows, candidate_numeric)
            for rel in relationships:
                boost = min(0.15, rel["match_ratio"] * 0.2)
                for col, stype in ((rel["weight"], "weight_kg"), (rel["money"], "money_total"), (rel["price"], "price_per_kg")):
                    current = columns.get(col, {})
                    if current.get("semantic_type") in {stype, "unknown"}:
                        current["semantic_type"] = stype
                        current["confidence"] = round(min(0.99, float(current.get("confidence", 0.0)) + boost), 3)
                        current["reason"] = f"{current.get('reason', '')}; relación matemática money≈weight*price"
                        columns[col] = current

            self.logger.info("Semantic inference sheet=%s columns=%s relationships=%s", table.get("sheet_name", ""), columns, relationships)
            results["tables"].append({"sheet_name": table.get("sheet_name", ""), "columns": columns, "relationships": relationships})
        return results

    def resolve_semantic_column(self, semantic_schema: dict, semantic_type: str, threshold: float | None = None) -> tuple[str | None, dict[str, Any]]:
        limit = self.confidence_threshold if threshold is None else threshold
        candidates: list[tuple[str, float]] = []
        for table in semantic_schema.get("tables", []):
            for col, meta in table.get("columns", {}).items():
                if meta.get("semantic_type") == semantic_type:
                    candidates.append((col, float(meta.get("confidence", 0.0))))
        if not candidates:
            return None, {"reason": "no_candidates", "candidates": []}
        candidates.sort(key=lambda x: x[1], reverse=True)
        best_col, best_conf = candidates[0]
        tie = len(candidates) > 1 and abs(candidates[0][1] - candidates[1][1]) < 0.05
        if best_conf < limit or tie:
            return None, {"reason": "low_confidence_or_tie", "candidates": candidates[:3]}
        return best_col, {"reason": "ok", "candidates": candidates[:3]}

    def _looks_date_like(self, value: Any) -> bool:
        text = str(value or "").strip()
        if not text:
            return False
        if re.match(r"^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}$", text):
            return True
        if re.match(r"^\d{4}-\d{1,2}-\d{1,2}", text):
            return True
        try:
            datetime.fromisoformat(text)
            return True
        except ValueError:
            return False

    def _to_float(self, value: Any) -> float | None:
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value or "").strip().replace(" ", "")
        if not text:
            return None
        if text.count(",") > 0 and text.count(".") > 0:
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", ".")
        try:
            return float(text)
        except ValueError:
            return None
