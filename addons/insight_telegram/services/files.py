"""Files a person sends the bot, as the content blocks a Claude model reads.

Images and PDFs go as they are, which the model reads natively; spreadsheets,
documents and text go as their text; anything else is named and measured.
What a file says is data for the model, never an instruction to it.
"""

import base64
import io
import logging
import zipfile

from lxml import etree

_logger = logging.getLogger(__name__)

IMAGE_TYPES = ("image/jpeg", "image/png", "image/gif", "image/webp")
MAX_BYTES = 20 * 1024 * 1024
# what an Office file may unpack to: a forwarded zip bomb is refused before
# it fills the worker's memory
MAX_UNPACKED = 100 * 1024 * 1024
MAX_TEXT = 60000
TEXT_EXTENSIONS = (
    ".txt",
    ".csv",
    ".tsv",
    ".json",
    ".xml",
    ".md",
    ".html",
    ".htm",
    ".log",
)


def blocks(files) -> list:
    """Content blocks for `files`, ``[(name, bytes, mimetype)]``."""
    result = []
    for name, content, mimetype in files:
        try:
            result += _blocks_of(name, content, (mimetype or "").lower())
        except Exception:
            _logger.info("insight_telegram could not read %s", name, exc_info=True)
            result.append(_text(name, f"[{len(content)} bytes that could not be read]"))
    return result


def _blocks_of(name, content, mimetype) -> list:
    lower = (name or "").lower()
    if len(content) > MAX_BYTES:
        return [_text(name, f"[{len(content)} bytes: too large to read]")]
    if mimetype in IMAGE_TYPES:
        return [_image(content, mimetype), _text(name, "[image above]")]
    if mimetype.startswith("image/"):
        return [_image(_as_png(content), "image/png"), _text(name, "[image above]")]
    if mimetype == "application/pdf" or lower.endswith(".pdf"):
        return [
            {
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": base64.b64encode(content).decode(),
                },
            },
            _text(name, "[PDF above]"),
        ]
    if lower.endswith((".xlsx", ".xlsm")) or "spreadsheetml" in mimetype:
        return [_text(name, _spreadsheet_text(content))]
    if lower.endswith(".docx") or "wordprocessingml" in mimetype:
        return [_text(name, _docx_text(content))]
    if mimetype.startswith("text/") or lower.endswith(TEXT_EXTENSIONS):
        return [_text(name, content.decode("utf-8", errors="replace"))]
    return [
        _text(
            name,
            f"[{mimetype or 'unknown type'}, {len(content)} bytes: not readable as text]",
        )
    ]


def _text(name, text) -> dict:
    text = text if len(text) <= MAX_TEXT else text[:MAX_TEXT] + "\n[TRUNCATED]"
    return {
        "type": "text",
        "text": f"<file name={name!r}>\n{text}\n</file>",
    }


def _image(content, mimetype) -> dict:
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": mimetype,
            "data": base64.b64encode(content).decode(),
        },
    }


def _as_png(content) -> bytes:
    from PIL import Image

    output = io.BytesIO()
    Image.open(io.BytesIO(content)).convert("RGB").save(output, format="PNG")
    return output.getvalue()


def _check_unpacked(content) -> None:
    """Refuse an Office file whose members unpack beyond MAX_UNPACKED."""
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        size = sum(info.file_size for info in archive.infolist())
    if size > MAX_UNPACKED:
        raise ValueError(f"unpacks to {size} bytes")


def _spreadsheet_text(content) -> str:
    from openpyxl import load_workbook

    _check_unpacked(content)
    workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    lines = []
    for sheet in workbook.worksheets:
        lines.append(f"## {sheet.title}")
        for row in sheet.iter_rows(values_only=True):
            if any(cell is not None for cell in row):
                lines.append(
                    "\t".join("" if cell is None else str(cell) for cell in row)
                )
            if len(lines) > 3000:
                lines.append("[more rows not shown]")
                return "\n".join(lines)
    return "\n".join(lines)


def _docx_text(content) -> str:
    _check_unpacked(content)
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    paragraphs = [
        "".join(node.text or "" for node in paragraph.iter(f"{namespace}t"))
        for paragraph in root.iter(f"{namespace}p")
    ]
    return "\n".join(text for text in paragraphs if text)
