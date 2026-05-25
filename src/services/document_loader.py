import csv
import logging
from pathlib import Path

from docx import Document
from openpyxl import load_workbook
from pypdf import PdfReader


class DocumentLoader:
    CSV_MAX_ROWS = 200
    XLSX_MAX_ROWS_PER_SHEET = 300
    INTERMEDIATE_CHAR_LIMIT = 120000

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)

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
        if extension == ".xlsx":
            return self._extract_xlsx(file_path)

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

    def _extract_xlsx(self, file_path: Path) -> str:
        wb = load_workbook(str(file_path), read_only=True, data_only=True)
        parts: list[str] = []
        for sheet in wb.worksheets:
            parts.append(f"[Hoja: {sheet.title}]")
            row_count = 0
            for row in sheet.iter_rows(values_only=True):
                values = ["" if value is None else str(value) for value in row]
                if not any(v.strip() for v in values):
                    continue
                parts.append("\t".join(values).rstrip())
                row_count += 1
                if row_count >= self.XLSX_MAX_ROWS_PER_SHEET or sum(len(x) for x in parts) >= self.INTERMEDIATE_CHAR_LIMIT:
                    break
        return "\n".join(parts)
