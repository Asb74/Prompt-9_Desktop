import argparse
from pathlib import Path

from src.services.table_loader import TableLoader


def _fmt_number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:.2f}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnóstico de lectura Excel para PROM-9")
    parser.add_argument("path", help="Ruta al archivo .xls/.xlsx/.csv")
    args = parser.parse_args()

    path = Path(args.path)
    loader = TableLoader()
    debug = loader.debug_table_scan(str(path))

    print(f"Archivo: {path}")
    print(f"Hojas: {', '.join(debug.get('sheets_found', []))}")
    for sheet in debug.get("sheets", []):
        print(f"- Hoja: {sheet['sheet_name']}")
        print(f"  Cabeceras detectadas: {sheet.get('detected_headers', [])}")
        print(f"  Bloques detectados: {sheet.get('blocks_detected', 0)}")
        print(f"  Variedades únicas: {sheet.get('unique_varieties', [])}")

    print("Kg por variedad:")
    for variety, total in debug.get("total_neto_by_variety", {}).items():
        print(f"{variety}: {_fmt_number(total)}")
    print(f"TOTAL: {_fmt_number(debug.get('total_neto_general', 0.0))}")
    print(f"Log: {debug.get('log_path', '')}")


if __name__ == "__main__":
    main()
