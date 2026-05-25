import csv
import logging
from pathlib import Path

from docx import Document
from pypdf import PdfReader

from src.services.spreadsheet_analyzer import SpreadsheetAnalyzer


class DocumentLoader:
    CSV_MAX_ROWS = 200
    XLSX_MAX_ROWS_PER_SHEET = 300
    XLS_MAX_ROWS_PER_SHEET = 300
    INTERMEDIATE_CHAR_LIMIT = 120000

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)
        self.spreadsheet_analyzer = SpreadsheetAnalyzer()

    def extract_text(self, path: str) -> str:
        file_path = Path(path)
        extension = file_path.suffix.lower()

        if extension == ".txt":
            return self._extract_txt(file_path)
        if extension == ".csv":
            return self._extract_csv(file_path)
        if extension == ".pdf":
            return self._extract_pdf(file_path)
        if extension == ".docx":
            return self._extract_docx(file_path)
        if extension in {".xlsx", ".xls"}:
            return self._extract_spreadsheet(file_path)

        raise ValueError(f"Formato de archivo no soportado: {extension}")

    def _extract_txt(self, file_path: Path) -> str:
        for encoding, kwargs in (("utf-8", {}), ("latin-1", {}), ("utf-8", {"errors": "replace"})):
            try:
                with file_path.open("r", encoding=encoding, **kwargs) as f:
                    return f.read()
            except UnicodeDecodeError:
                continue
        return ""

    def _extract_csv(self, file_path: Path) -> str:
        rows: list[str] = []
        with file_path.open("r", encoding="utf-8", errors="replace", newline="") as f:
            reader = csv.reader(f)
            for i, row in enumerate(reader):
                if i >= self.CSV_MAX_ROWS:
                    break
                rows.append("\t".join(str(cell) for cell in row))
                if sum(len(x) for x in rows) >= self.INTERMEDIATE_CHAR_LIMIT:
                    break
        return "\n".join(rows)

    def _extract_pdf(self, file_path: Path) -> str:
        reader = PdfReader(str(file_path))
        chunks: list[str] = []
        for idx, page in enumerate(reader.pages, start=1):
            try:
                page_text = page.extract_text() or ""
            except Exception:
                self.logger.warning("No se pudo extraer texto de página %s en PDF %s", idx, file_path.name)
                continue
            if page_text.strip():
                chunks.append(page_text)
            if sum(len(x) for x in chunks) >= self.INTERMEDIATE_CHAR_LIMIT:
                break
        return "\n\n".join(chunks)

    def _extract_docx(self, file_path: Path) -> str:
        doc = Document(str(file_path))
        parts: list[str] = []
        for paragraph in doc.paragraphs:
            text = (paragraph.text or "").strip()
            if text:
                parts.append(text)
        for table in doc.tables:
            for row in table.rows:
                cells = [((cell.text or "").strip()) for cell in row.cells]
                if any(cells):
                    parts.append("\t".join(cells))
                if sum(len(x) for x in parts) >= self.INTERMEDIATE_CHAR_LIMIT:
                    break
        return "\n".join(parts)

    def _extract_spreadsheet(self, file_path: Path) -> str:
        tables = self.spreadsheet_analyzer.load_workbook_tables(str(file_path))
        parts: list[str] = []
        for table in tables:
            parts.append(f"[Hoja: {table['sheet']}]")
            parts.append("Columnas detectadas:")
            parts.append(" | ".join(str(col) for col in table["headers"]))
            parts.append("")
            parts.append("Filas:")
            for row in table["rows"][: self.XLSX_MAX_ROWS_PER_SHEET]:
                pairs = [f"{header}={row.get(header, '')}" for header in table["headers"]]
                parts.append(" | ".join(pairs))
                if sum(len(x) for x in parts) >= self.INTERMEDIATE_CHAR_LIMIT:
                    break
            parts.append("")
            if sum(len(x) for x in parts) >= self.INTERMEDIATE_CHAR_LIMIT:
                break
        return "\n".join(parts)
