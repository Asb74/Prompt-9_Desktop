import csv
import logging
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

try:
    import xlrd  # type: ignore
except Exception:  # pragma: no cover
    xlrd = None


class TableLoader:
    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)

    def load_tables(self, path: str) -> list[dict[str, Any]]:
        extension = Path(path).suffix.lower()
        if extension == ".xlsx":
            return self._load_xlsx(path)
        if extension == ".xls":
            return self._load_xls(path)
        if extension == ".csv":
            return self._load_csv(path)
        raise ValueError(f"Formato tabular no soportado: {extension}")

    def _load_xlsx(self, path: str) -> list[dict[str, Any]]:
        wb = load_workbook(path, read_only=True, data_only=True)
        tables: list[dict[str, Any]] = []
        for sheet in wb.worksheets:
            rows = [list(row) for row in sheet.iter_rows(values_only=True)]
            table = self._build_table(sheet.title, rows)
            if table:
                tables.append(table)
        self.logger.info("TableLoader xlsx: hojas_detectadas=%s", len(tables))
        return tables

    def _load_xls(self, path: str) -> list[dict[str, Any]]:
        if xlrd is None:
            raise RuntimeError("xlrd no está instalado para procesar .xls")
        book = xlrd.open_workbook(path, on_demand=True)
        tables: list[dict[str, Any]] = []
        for sheet in book.sheets():
            rows = [sheet.row_values(row_idx) for row_idx in range(sheet.nrows)]
            table = self._build_table(sheet.name, rows)
            if table:
                tables.append(table)
        self.logger.info("TableLoader xls: hojas_detectadas=%s", len(tables))
        return tables

    def _load_csv(self, path: str) -> list[dict[str, Any]]:
        rows: list[list[Any]] = []
        with open(path, "r", encoding="utf-8", errors="replace", newline="") as f:
            reader = csv.reader(f)
            for row in reader:
                rows.append(row)
        table = self._build_table("CSV", rows)
        tables = [table] if table else []
        self.logger.info("TableLoader csv: tablas_detectadas=%s", len(tables))
        return tables

    def _detect_headers(self, rows: list[list[Any]]) -> tuple[int, list[str]]:
        for idx, row in enumerate(rows[:50]):
            values = ["" if v is None else str(v).strip() for v in row]
            non_empty = [v for v in values if v]
            if len(non_empty) >= 2:
                headers = [v if v else f"col_{col + 1}" for col, v in enumerate(values)]
                return idx, headers
        return 0, []

    def _build_table(self, sheet_name: str, rows: list[list[Any]]) -> dict[str, Any] | None:
        if not rows:
            return None
        header_idx, headers = self._detect_headers(rows)
        if not headers:
            return None
        data_rows: list[dict[str, Any]] = []
        for row in rows[header_idx + 1 :]:
            padded = list(row) + [None] * max(0, len(headers) - len(row))
            record = {headers[i]: self._normalize_cell(padded[i]) for i in range(len(headers))}
            if any(str(v).strip() for v in record.values() if v is not None):
                data_rows.append(record)
        self.logger.info("TableLoader: hoja=%s filas=%s columnas=%s", sheet_name, len(data_rows), len(headers))
        return {"sheet_name": sheet_name, "headers": headers, "rows": data_rows}

    def _normalize_cell(self, value: Any) -> Any:
        if value is None:
            return ""
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).strip()
        if not text:
            return ""
        number = self._parse_number(text)
        if number is not None:
            return number
        return text

    def _parse_number(self, raw: str) -> float | None:
        cleaned = raw.replace(" ", "")
        if not cleaned:
            return None
        has_comma = "," in cleaned
        has_dot = "." in cleaned
        if has_comma and has_dot:
            last_comma = cleaned.rfind(",")
            last_dot = cleaned.rfind(".")
            if last_comma > last_dot:
                cleaned = cleaned.replace(".", "").replace(",", ".")
            else:
                cleaned = cleaned.replace(",", "")
        elif has_comma:
            cleaned = cleaned.replace(",", ".")
        try:
            return float(cleaned)
        except ValueError:
            return None
