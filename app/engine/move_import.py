"""Import structured custom line-dance moves from common dancer-friendly files.

The importer accepts a small, transparent schema from JSON, CSV/TSV, XLSX,
DOCX, TXT/MD, and text-based PDFs.  It never guesses technical mechanics from
prose: rows missing counts, free-foot, end-foot, or clear instructions are
returned for review rather than being placed into the choreography library.
"""
from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from xml.etree import ElementTree as ET

from . import steps


MAX_IMPORT_BYTES = 8 * 1024 * 1024
SUPPORTED_EXTENSIONS = {".json", ".csv", ".tsv", ".txt", ".md", ".xlsx", ".docx", ".pdf"}
FIELD_ALIASES = {
    "move": "name", "move name": "name", "step": "name", "step name": "name",
    "count": "counts", "count(s)": "counts", "net rotation": "rotation",
    "net rotation deg": "rotation", "net rotation degrees": "rotation", "turn": "rotation",
    "foot start": "start", "start foot": "start", "free foot start": "start",
    "foot end": "end", "end foot": "end", "free foot end": "end",
    "travels": "travel", "travel direction": "travel", "direction": "travel",
    "teaching instructions": "instructions", "footwork": "instructions",
    "description": "instructions", "notes": "instructions",
    "generator eligible": "in_generator", "auto generate": "in_generator",
}


class MoveImportError(ValueError):
    pass


def _normal_key(value):
    value = re.sub(r"[_\-]+", " ", str(value or "").strip().lower())
    return re.sub(r"\s+", " ", value)


def _normal_record(record):
    if not isinstance(record, dict):
        return {}
    result = {}
    for key, value in record.items():
        key = FIELD_ALIASES.get(_normal_key(key), _normal_key(key).replace(" ", "_"))
        if value is not None and str(value).strip():
            result[key] = str(value).strip() if not isinstance(value, bool) else value
    return result


def _records_from_delimited(text, delimiter=None):
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return []
    if delimiter is None:
        delimiter = "\t" if "\t" in lines[0] else ","
    reader = csv.DictReader(io.StringIO("\n".join(lines)), delimiter=delimiter)
    if not reader.fieldnames:
        return _records_from_text(text)
    return [_normal_record(row) for row in reader]


def _records_from_text(text):
    """Pipe rows are ideal for Notepad/PDF/Word prose imports.

    Header format: Name | Counts | Start | End | Rotation | Level | Travel | Instructions
    The same named columns work in CSV, XLSX, and Word tables.
    """
    lines = [line.strip() for line in text.replace("\r", "").split("\n") if line.strip()]
    if not lines:
        return []
    pipe_rows = [[cell.strip() for cell in line.split("|")] for line in lines if "|" in line]
    if pipe_rows:
        first = [_normal_key(cell) for cell in pipe_rows[0]]
        known = sum(cell in FIELD_ALIASES or cell in ("name", "counts", "start", "end", "rotation", "level", "travel", "instructions")
                    for cell in first)
        if known >= 2:
            headers = pipe_rows[0]
            return [_normal_record(dict(zip(headers, row))) for row in pipe_rows[1:]]
        fields = ["name", "counts", "start", "end", "rotation", "level", "travel", "instructions"]
        return [_normal_record(dict(zip(fields, row))) for row in pipe_rows]
    # Plain reference text remains useful: show each line as a review item
    # instead of pretending its unmeasured mechanics are complete.
    return [{"name": line} for line in lines]


def _records_from_json(payload):
    try:
        value = json.loads(payload.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MoveImportError(f"This JSON file could not be read: {exc}")
    rows = value.get("moves") if isinstance(value, dict) else value
    if not isinstance(rows, list):
        raise MoveImportError("JSON must be a list of moves or an object with a moves list.")
    return [_normal_record(row) for row in rows]


def _xlsx_rows(payload):
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    rel_ns = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
        sheet_names = sorted(name for name in archive.namelist()
                             if name.startswith("xl/worksheets/") and name.endswith(".xml"))
        if not sheet_names:
            raise MoveImportError("The workbook has no readable worksheets.")
        shared = []
        if "xl/sharedStrings.xml" in archive.namelist():
            shared_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            shared = ["".join(node.itertext()) for node in shared_root.findall(f"{ns}si")]
        root = ET.fromstring(archive.read(sheet_names[0]))
    except zipfile.BadZipFile:
        raise MoveImportError("This does not look like an XLSX workbook. Save old .xls files as .xlsx first.")
    except ET.ParseError as exc:
        raise MoveImportError(f"The workbook could not be read: {exc}")

    rows = []
    for row in root.findall(f".//{ns}sheetData/{ns}row"):
        values = []
        for cell in row.findall(f"{ns}c"):
            ref = cell.get("r", "A1")
            letters = re.match(r"([A-Z]+)", ref)
            column = 0
            for letter in (letters.group(1) if letters else "A"):
                column = column * 26 + ord(letter) - 64
            while len(values) < column - 1:
                values.append("")
            inline = cell.find(f"{ns}is")
            value_node = cell.find(f"{ns}v")
            value = "".join(inline.itertext()) if inline is not None else (value_node.text if value_node is not None else "")
            if cell.get("t") == "s" and value:
                try:
                    value = shared[int(value)]
                except (ValueError, IndexError):
                    value = ""
            values.append(value or "")
        if any(str(value).strip() for value in values):
            rows.append(values)
    if not rows:
        return []
    headers = rows[0]
    return [_normal_record(dict(zip(headers, row))) for row in rows[1:]]


def _docx_rows(payload):
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
        root = ET.fromstring(archive.read("word/document.xml"))
    except (zipfile.BadZipFile, KeyError):
        raise MoveImportError("This Word file could not be read. Save it as a modern .docx file first.")
    except ET.ParseError as exc:
        raise MoveImportError(f"The Word file could not be read: {exc}")
    table_rows = []
    for row in root.findall(f".//{ns}tr"):
        cells = ["".join(cell.itertext()).strip() for cell in row.findall(f"{ns}tc")]
        if any(cells):
            table_rows.append(cells)
    if len(table_rows) >= 2:
        headers = table_rows[0]
        return [_normal_record(dict(zip(headers, row))) for row in table_rows[1:]]
    text = "\n".join("".join(paragraph.itertext()) for paragraph in root.findall(f".//{ns}p"))
    return _records_from_text(text)


def _pdf_rows(payload):
    try:
        from pypdf import PdfReader
    except ImportError:
        raise MoveImportError("PDF import needs the small optional pypdf component. Install it, then restart Line Dance Creator.")
    try:
        reader = PdfReader(io.BytesIO(payload))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:
        raise MoveImportError(f"This PDF could not be read as text: {exc}")
    return _records_from_text(text)


def extract_records(filename, payload):
    if len(payload) > MAX_IMPORT_BYTES:
        raise MoveImportError("Move-library imports must be 8 MB or smaller.")
    extension = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension not in SUPPORTED_EXTENSIONS:
        allowed = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise MoveImportError(f"Use one of these formats: {allowed}.")
    if extension == ".json":
        return _records_from_json(payload)
    if extension in (".csv", ".tsv"):
        return _records_from_delimited(payload.decode("utf-8-sig", errors="replace"), "\t" if extension == ".tsv" else ",")
    if extension in (".txt", ".md"):
        return _records_from_text(payload.decode("utf-8-sig", errors="replace"))
    if extension == ".xlsx":
        return _xlsx_rows(payload)
    if extension == ".docx":
        return _docx_rows(payload)
    return _pdf_rows(payload)


def import_moves(filename, payload):
    records = extract_records(filename, payload)
    accepted, review = [], []
    for number, record in enumerate(records, start=1):
        try:
            move = steps.save_custom_move(record)
            accepted.append({"id": move["move_id"], "name": move["name"]})
        except ValueError as exc:
            review.append({"row": number, "name": record.get("name") or "Unnamed row",
                           "reason": str(exc)})
    return {"file": filename, "found": len(records), "accepted": accepted,
            "needs_review": review}


def template():
    return {
        "moves": [{
            "name": "Example Side Rock", "counts": 2, "start": "R", "end": "R",
            "rotation": 0, "level": "Beginner", "travel": "", "sync": False,
            "instructions": "Rock R to right side, recover weight to L.",
            "in_generator": False,
        }]
    }
