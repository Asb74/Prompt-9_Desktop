from collections import defaultdict
from typing import Any


class TableAnalysisEngine:
    def run(self, tables: list[dict[str, Any]], semantic_columns: dict[str, str], intent: dict[str, Any]) -> dict[str, Any]:
        operation = intent.get("operation")
        if operation == "count":
            return {"count": self.count_rows(tables)}
        if operation == "total_general":
            metric = intent["metrics"][0]
            return {"total_general": self.aggregate_sum(tables, semantic_columns.get(metric["column"], ""))}
        if operation in {"group_sum", "group_avg", "group_weighted_average"}:
            group_col = semantic_columns.get(intent["group_by"][0], "")
            metric_col = semantic_columns.get(intent["metrics"][0]["column"], "")
            if operation == "group_sum":
                result = self.aggregate_sum(tables, metric_col, group_col)
            elif operation == "group_avg":
                result = self.aggregate_average(tables, metric_col, group_col)
            else:
                result = self.aggregate_weighted_average(tables, group_col, semantic_columns.get("importe", ""), semantic_columns.get("neto", ""))
            result = self.sort_results(result, intent.get("sort"))
            if intent.get("limit"):
                result = self.top_n(result, int(intent["limit"]))
            return result
        if operation == "sum":
            metric_col = semantic_columns.get(intent["metrics"][0]["column"], "")
            return {"sum": self.aggregate_sum(tables, metric_col)}
        if operation == "avg":
            metric_col = semantic_columns.get(intent["metrics"][0]["column"], "")
            return {"average": self.aggregate_average(tables, metric_col)}
        if operation == "weighted_average":
            return {
                "weighted_average": self.aggregate_weighted_average(
                    tables,
                    None,
                    semantic_columns.get("importe", ""),
                    semantic_columns.get("neto", ""),
                )
            }
        return {}

    def aggregate_sum(self, tables: list[dict[str, Any]], value_col: str, group_col: str | None = None) -> Any:
        if not value_col:
            return {}
        if group_col:
            grouped: defaultdict[str, float] = defaultdict(float)
            for row in self._iter_rows(tables):
                key = str(row.get(group_col, "")).strip()
                if not key:
                    continue
                grouped[key] += self._to_float(row.get(value_col))
            return dict(grouped)
        total = 0.0
        for row in self._iter_rows(tables):
            total += self._to_float(row.get(value_col))
        return total

    def aggregate_average(self, tables: list[dict[str, Any]], value_col: str, group_col: str | None = None) -> Any:
        if not value_col:
            return {}
        if group_col:
            acc: defaultdict[str, list[float]] = defaultdict(list)
            for row in self._iter_rows(tables):
                key = str(row.get(group_col, "")).strip()
                if not key:
                    continue
                acc[key].append(self._to_float(row.get(value_col)))
            return {k: (sum(v) / len(v) if v else 0.0) for k, v in acc.items()}
        values = [self._to_float(row.get(value_col)) for row in self._iter_rows(tables)]
        return sum(values) / len(values) if values else 0.0

    def aggregate_weighted_average(self, tables: list[dict[str, Any]], group_col: str | None, amount_col: str, weight_col: str) -> Any:
        if not amount_col or not weight_col:
            return {}
        if group_col:
            numerator: defaultdict[str, float] = defaultdict(float)
            denominator: defaultdict[str, float] = defaultdict(float)
            for row in self._iter_rows(tables):
                key = str(row.get(group_col, "")).strip()
                if not key:
                    continue
                numerator[key] += self._to_float(row.get(amount_col))
                denominator[key] += self._to_float(row.get(weight_col))
            return {k: (numerator[k] / denominator[k] if denominator[k] else 0.0) for k in numerator}
        total_amount = 0.0
        total_weight = 0.0
        for row in self._iter_rows(tables):
            total_amount += self._to_float(row.get(amount_col))
            total_weight += self._to_float(row.get(weight_col))
        return total_amount / total_weight if total_weight else 0.0

    def count_rows(self, tables: list[dict[str, Any]]) -> int:
        return sum(len(table.get("rows", [])) for table in tables)

    def top_n(self, values: dict[str, float], n: int) -> dict[str, float]:
        return dict(list(values.items())[: max(0, n)])

    def sort_results(self, values: dict[str, float], direction: str | None) -> dict[str, float]:
        if direction not in {"asc", "desc"}:
            return values
        reverse = direction == "desc"
        return dict(sorted(values.items(), key=lambda item: item[1], reverse=reverse))

    def _iter_rows(self, tables: list[dict[str, Any]]):
        for table in tables:
            for row in table.get("rows", []):
                yield row

    def _to_float(self, value: Any) -> float:
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value or "").strip().replace(" ", "")
        if not text:
            return 0.0
        text = text.replace(",", ".")
        try:
            return float(text)
        except ValueError:
            return 0.0
