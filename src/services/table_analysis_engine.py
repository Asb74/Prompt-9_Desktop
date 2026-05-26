import logging
import unicodedata
from collections import defaultdict
from typing import Any


class TableAnalysisEngine:
    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)

    def run_analysis(self, tables: list[dict[str, Any]], intent: dict[str, Any]) -> dict[str, Any]:
        operation = intent.get("operation")
        if operation == "aggregate_sum":
            return self.aggregate_sum(tables, str(intent.get("group_by", "")), str(intent.get("value_column", "")))
        if operation == "total_sum":
            return self.total_sum(tables, str(intent.get("value_column", "")))
        if operation == "count_by":
            return self.count_by(tables, str(intent.get("group_by", "")))
        if operation == "average":
            return self.average(tables, str(intent.get("group_by", "")), str(intent.get("value_column", "")))
        if operation == "weighted_average":
            result = self.weighted_average(
                tables,
                str(intent.get("group_by", "")),
                str(intent.get("numerator_column", "")),
                str(intent.get("denominator_column", "")),
            )
            if intent.get("top_n"):
                return self.top_n(result, int(intent.get("top_n", 10)))
            return result
        raise ValueError(f"Operación no soportada: {operation}")

    def aggregate_sum(self, tables: list[dict[str, Any]], group_by: str, value_column: str) -> dict[str, Any]:
        gcol, vcol, headers = self._resolve_columns(tables, group_by, value_column)
        grouped: dict[str, float] = defaultdict(float)
        rows_processed = 0
        ignored_rows = 0

        for row in self._iter_rows(tables):
            rows_processed += 1
            group_value = self._clean_group(row.get(gcol))
            if not group_value:
                ignored_rows += 1
                continue
            numeric_value = self._to_float(row.get(vcol))
            if numeric_value is None:
                ignored_rows += 1
                continue
            grouped[group_value] += numeric_value

        result = [{"group": k, "value": v} for k, v in sorted(grouped.items(), key=lambda item: item[1], reverse=True)]
        payload = {
            "operation": "aggregate_sum",
            "group_by": gcol,
            "value_column": vcol,
            "rows_processed": rows_processed,
            "rows_ignored": ignored_rows,
            "groups": len(grouped),
            "result": result,
            "total": sum(grouped.values()),
        }
        self._log_operation(payload, headers)
        return payload

    def total_sum(self, tables: list[dict[str, Any]], value_column: str) -> dict[str, Any]:
        _, vcol, headers = self._resolve_columns(tables, None, value_column)
        total = 0.0
        rows_processed = 0
        ignored_rows = 0
        for row in self._iter_rows(tables):
            rows_processed += 1
            numeric_value = self._to_float(row.get(vcol))
            if numeric_value is None:
                ignored_rows += 1
                continue
            total += numeric_value
        payload = {
            "operation": "total_sum",
            "value_column": vcol,
            "rows_processed": rows_processed,
            "rows_ignored": ignored_rows,
            "result": [{"group": "TOTAL", "value": total}],
            "total": total,
        }
        self._log_operation(payload, headers)
        return payload

    def count_by(self, tables: list[dict[str, Any]], group_by: str) -> dict[str, Any]:
        gcol, _, headers = self._resolve_columns(tables, group_by, None)
        grouped: dict[str, int] = defaultdict(int)
        rows_processed = 0
        ignored_rows = 0
        for row in self._iter_rows(tables):
            rows_processed += 1
            group_value = self._clean_group(row.get(gcol))
            if not group_value:
                ignored_rows += 1
                continue
            grouped[group_value] += 1
        result = [{"group": k, "value": v} for k, v in sorted(grouped.items(), key=lambda item: item[1], reverse=True)]
        payload = {
            "operation": "count_by",
            "group_by": gcol,
            "rows_processed": rows_processed,
            "rows_ignored": ignored_rows,
            "groups": len(grouped),
            "result": result,
            "total": sum(grouped.values()),
        }
        self._log_operation(payload, headers)
        return payload

    def average(self, tables: list[dict[str, Any]], group_by: str, value_column: str) -> dict[str, Any]:
        gcol, vcol, headers = self._resolve_columns(tables, group_by, value_column)
        sums: dict[str, float] = defaultdict(float)
        counts: dict[str, int] = defaultdict(int)
        rows_processed = 0
        ignored_rows = 0
        for row in self._iter_rows(tables):
            rows_processed += 1
            group_value = self._clean_group(row.get(gcol))
            if not group_value:
                ignored_rows += 1
                continue
            numeric_value = self._to_float(row.get(vcol))
            if numeric_value is None:
                ignored_rows += 1
                continue
            sums[group_value] += numeric_value
            counts[group_value] += 1
        result = [{"group": k, "value": (sums[k] / counts[k])} for k in sums]
        result.sort(key=lambda item: item["value"], reverse=True)
        payload = {
            "operation": "average",
            "group_by": gcol,
            "value_column": vcol,
            "rows_processed": rows_processed,
            "rows_ignored": ignored_rows,
            "groups": len(result),
            "result": result,
        }
        self._log_operation(payload, headers)
        return payload

    def weighted_average(self, tables: list[dict[str, Any]], group_by: str, numerator_column: str, denominator_column: str) -> dict[str, Any]:
        gcol, ncol, headers = self._resolve_columns(tables, group_by, numerator_column)
        dcol = self.find_column(headers, denominator_column)
        if not dcol:
            raise ValueError(f"No se encontró la columna solicitada: {denominator_column}")
        numerator: dict[str, float] = defaultdict(float)
        denominator: dict[str, float] = defaultdict(float)
        rows_processed = 0
        ignored_rows = 0
        for row in self._iter_rows(tables):
            rows_processed += 1
            group_value = self._clean_group(row.get(gcol))
            if not group_value:
                ignored_rows += 1
                continue
            num = self._to_float(row.get(ncol))
            den = self._to_float(row.get(dcol))
            if num is None or den is None:
                ignored_rows += 1
                continue
            numerator[group_value] += num
            denominator[group_value] += den
        result = []
        for key in numerator:
            if denominator[key] == 0:
                continue
            result.append({"group": key, "value": numerator[key] / denominator[key]})
        result.sort(key=lambda item: item["value"], reverse=True)
        payload = {
            "operation": "weighted_average",
            "group_by": gcol,
            "numerator_column": ncol,
            "denominator_column": dcol,
            "rows_processed": rows_processed,
            "rows_ignored": ignored_rows,
            "groups": len(result),
            "result": result,
        }
        self._log_operation(payload, headers)
        return payload

    def top_n(self, result: dict[str, Any], n: int = 10, reverse: bool = True) -> dict[str, Any]:
        rows = list(result.get("result", []))
        rows.sort(key=lambda item: item.get("value", 0), reverse=reverse)
        result["result"] = rows[: max(0, n)]
        result["top_n"] = n
        return result

    def find_column(self, headers: list[str], requested_name: str) -> str | None:
        normalized_requested = self._normalize(requested_name)
        if not normalized_requested:
            return None
        exact = {self._normalize(header): header for header in headers}
        if normalized_requested in exact:
            return exact[normalized_requested]
        partial_matches = [header for header in headers if normalized_requested in self._normalize(header)]
        if partial_matches:
            return partial_matches[0]
        return None

    def _resolve_columns(self, tables: list[dict[str, Any]], group_by: str | None, value_column: str | None) -> tuple[str | None, str | None, list[str]]:
        headers = self._collect_headers(tables)
        resolved_group = self.find_column(headers, group_by) if group_by else None
        resolved_value = self.find_column(headers, value_column) if value_column else None
        if group_by and not resolved_group:
            raise ValueError(f"No se encontró la columna solicitada: {group_by}")
        if value_column and not resolved_value:
            raise ValueError(f"No se encontró la columna solicitada: {value_column}")
        return resolved_group, resolved_value, headers

    def _collect_headers(self, tables: list[dict[str, Any]]) -> list[str]:
        headers: list[str] = []
        for table in tables:
            headers.extend(table.get("headers", []))
        return headers

    def _normalize(self, value: str) -> str:
        text = unicodedata.normalize("NFD", str(value or ""))
        text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
        return "".join(text.lower().split())

    def _clean_group(self, value: Any) -> str:
        return str(value or "").strip()

    def _to_float(self, value: Any) -> float | None:
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value or "").strip()
        if not text:
            return None
        text = text.replace(" ", "")
        if text.count(",") > 0 and text.count(".") > 0:
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", ".")
        try:
            return float(text)
        except ValueError:
            return None

    def _iter_rows(self, tables: list[dict[str, Any]]):
        for table in tables:
            for row in table.get("rows", []):
                yield row

    def _log_operation(self, payload: dict[str, Any], headers: list[str]) -> None:
        self.logger.info(
            "TableAnalysis operation=%s columns=%s rows_processed=%s rows_ignored=%s groups=%s headers=%s",
            payload.get("operation"),
            {k: v for k, v in payload.items() if "column" in k or k == "group_by"},
            payload.get("rows_processed", 0),
            payload.get("rows_ignored", 0),
            payload.get("groups", 0),
            len(headers),
        )
