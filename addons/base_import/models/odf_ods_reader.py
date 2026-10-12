from odf import opendocument
from odf.table import Table, TableCell, TableRow
from odf.text import P

from .zip_guard import check_zip_member_sizes

MAX_CELL_REPEAT = 16384
MAX_ROW_REPEAT = 16384

_ELEMENT_NODE = 1
_TEXT_NODE = 3


def _repeat_count(element, attribute, cap):
    try:
        count = int(element.getAttribute(attribute) or 1)
    except ValueError:
        return 1
    return max(0, min(count, cap))


def _cell_text(cell) -> str:
    return "".join(_node_text(paragraph) for paragraph in cell.getElementsByType(P))


def _node_text(node) -> str:
    parts = []
    for child in node.childNodes:
        if child.nodeType == _TEXT_NODE:
            parts.append(child.data)
        elif child.nodeType == _ELEMENT_NODE:
            parts.append(_node_text(child))
    return "".join(parts)


class ODSReader:
    def __init__(self, file=None, content=None) -> None:
        if content is None:
            check_zip_member_sizes(file)
        self.doc = content if content is not None else opendocument.load(file)
        self.sheets = {}
        for sheet in self.doc.spreadsheet.getElementsByType(Table):
            name = sheet.getAttribute("name")
            self.sheets.setdefault(name, self._read_sheet(sheet))

    def _read_sheet(self, sheet):
        rows = []
        for row in sheet.getElementsByType(TableRow):
            cells = self._read_row(row)
            if not any(cell.strip() for cell in cells):
                continue
            repeat = _repeat_count(row, "numberrowsrepeated", MAX_ROW_REPEAT)
            rows.extend([cells] * repeat)
        return rows

    def _read_row(self, row):
        cells = []
        elements = row.getElementsByType(TableCell)
        for position, cell in enumerate(elements, start=1):
            text = _cell_text(cell)
            if position == len(elements) and not text.strip():
                repeat = 1
            else:
                repeat = _repeat_count(cell, "numbercolumnsrepeated", MAX_CELL_REPEAT)
            cells.extend([text] * repeat)
        return cells

    def get_sheet(self, name):
        return self.sheets[name]
