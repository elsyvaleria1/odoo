import io
from collections import deque

import xlsxwriter
from werkzeug.datastructures import FileStorage

from odoo import http
from odoo.http import (
    BadRequest,
    Response,
    UnprocessableEntity,
    prepare_content_disposition_header,
    request,
)
from odoo.libs.debug_log import DebugLog
from odoo.libs.documents import extension_for
from odoo.libs.filesystem import osutil
from odoo.libs.json import loads as json_loads
from odoo.tools import LazyTranslate

from .export_writers import XLSX_MIMETYPE

_lt = LazyTranslate(__name__)
_debug = DebugLog(__name__)

MAX_EXPORT_CELLS = 1_000_000

MAX_CELL_CHARS = 32_767


def _get_capped_cell(value):
    return value[:MAX_CELL_CHARS] if isinstance(value, str) else value


def _clamp_int(value, hi):
    try:
        return max(0, min(int(value), hi))
    except TypeError, ValueError:
        return 0


class _CappedWorksheet:
    def __init__(self, worksheet, cap: int, title: str) -> None:
        self._worksheet = worksheet
        self._cap = cap
        self._title = title
        self.cells_written = 0

    def __getattr__(self, name):
        return getattr(self._worksheet, name)

    def write(self, *args, **kwargs):
        self.cells_written += 1
        if self.cells_written > self._cap:
            _debug.logic("export_xlsx_cell_cap_hit", title=self._title, cap=self._cap)
            raise UnprocessableEntity(
                _lt(
                    "This pivot is too large to export (over %s cells). "
                    "Narrow the grouping or add filters and try again.",
                    self._cap,
                )
            )
        return self._worksheet.write(*args, **kwargs)


class TableExporter(http.Controller):
    @http.route("/web/pivot/export_xlsx", type="http", auth="user", readonly=True)
    def export_xlsx(self, data: str | FileStorage, **kw) -> Response:
        try:
            jdata = json_loads(data.read() if isinstance(data, FileStorage) else data)
        except ValueError as exc:
            _debug.logic("export_xlsx_payload_not_json")
            raise BadRequest("The pivot export payload is not valid JSON.") from exc
        if not isinstance(jdata, dict):
            _debug.logic("export_xlsx_payload_not_object", payload=type(jdata).__name__)
            raise BadRequest("The pivot export payload must be a JSON object.")
        if _debug.lifecycle.enabled:
            _debug.lifecycle(
                "export_xlsx",
                payload="file" if isinstance(data, FileStorage) else "string",
                keys=sorted(jdata),
            )
        if not jdata:
            _debug.logic("export_xlsx_empty_payload")
            raise UnprocessableEntity(request.env._("No data to export"))
        _debug.perf.count(
            "export_xlsx_payload_size",
            title=jdata.get("title"),
            header_rows=len(jdata.get("col_group_headers", ())),
            measures=len(jdata.get("measure_headers", ())),
            rows=len(jdata.get("rows", ())),
        )
        output = io.BytesIO()
        with xlsxwriter.Workbook(
            output, {"in_memory": True, "strings_to_formulas": False}
        ) as workbook:
            worksheet = _CappedWorksheet(
                workbook.add_worksheet(jdata["title"]), MAX_EXPORT_CELLS, jdata["title"]
            )

            header_bold = workbook.add_format(
                {"bold": True, "pattern": 1, "bg_color": "#AAAAAA"}
            )
            header_plain = workbook.add_format({"pattern": 1, "bg_color": "#AAAAAA"})
            bold = workbook.add_format({"bold": True})

            measure_count = _clamp_int(jdata["measure_count"], 100000)

            with _debug.perf(
                "export_xlsx_write_sheet", cr=request.env.cr, title=jdata.get("title")
            ):
                y = self._write_pivot_col_headers(
                    worksheet, jdata, header_plain, measure_count
                )
                y = self._write_pivot_measure_headers(
                    worksheet, jdata, y, header_bold, header_plain
                )
                worksheet.freeze_panes(y, 1)
                self._write_pivot_rows(worksheet, jdata, y, header_plain, bold)
            _debug.pipeline(
                "export_xlsx_sheet_written",
                title=jdata.get("title"),
                cells=worksheet.cells_written,
                header_height=y,
            )

            with _debug.perf(
                "export_xlsx_autofit", cr=request.env.cr, title=jdata.get("title")
            ):
                worksheet.autofit()

        xlsx_data = output.getvalue()
        _debug.perf.count(
            "export_xlsx_size", title=jdata.get("title"), size=len(xlsx_data)
        )
        filename = osutil.clean_filename(
            request.env._(
                "Pivot %(title)s (%(model_name)s)",
                title=jdata["title"],
                model_name=jdata["model"],
            )
        )
        return request.prepare_response(
            xlsx_data,
            headers=[
                ("Content-Type", XLSX_MIMETYPE),
                (
                    "Content-Disposition",
                    prepare_content_disposition_header(
                        f"{filename}.{extension_for(XLSX_MIMETYPE)}"
                    ),
                ),
            ],
        )

    @_debug.perf.timed
    def _write_pivot_col_headers(self, worksheet, jdata, header_plain, measure_count):
        x, y = 1, 0
        carry: deque[dict[str, int]] = deque()

        def flush_carry(x):
            while carry and carry[0]["x"] == x:
                cell = carry.popleft()
                for j in range(measure_count):
                    worksheet.write(y, x + j, "", header_plain)
                if cell["height"] > 1:
                    carry.append({"x": x, "height": cell["height"] - 1})
                x += measure_count
            return x

        for header_row in jdata["col_group_headers"]:
            worksheet.write(y, 0, "", header_plain)
            for header in header_row:
                x = flush_carry(x)
                width = _clamp_int(header["width"], 100000)
                height = _clamp_int(header["height"], 100000)
                for j in range(width):
                    worksheet.write(
                        y,
                        x + j,
                        _get_capped_cell(header["title"]) if j == 0 else "",
                        header_plain,
                    )
                if height > 1:
                    carry.append({"x": x, "height": height - 1})
                x += width
            x = flush_carry(x)
            x, y = 1, y + 1
        return y

    @_debug.perf.timed
    def _write_pivot_measure_headers(
        self, worksheet, jdata, y, header_bold, header_plain
    ):
        measure_headers = jdata["measure_headers"]
        if not measure_headers:
            _debug.logic("no_measure_headers_row_skipped", row=y)
            return y
        worksheet.write(y, 0, "", header_plain)
        for x, measure in enumerate(measure_headers, start=1):
            style = header_bold if measure["is_bold"] else header_plain
            worksheet.write(y, x, _get_capped_cell(measure["title"]), style)
        return y + 1

    @_debug.perf.timed
    def _write_pivot_rows(self, worksheet, jdata, y, header_plain, bold):
        for row in jdata["rows"]:
            indent = _clamp_int(row.get("indent", 0), 50)
            worksheet.write(
                y,
                0,
                f"{indent * '     '}{_get_capped_cell(row['title'])}",
                header_plain,
            )
            for x, cell in enumerate(row["values"], start=1):
                if cell.get("is_bold", False):
                    worksheet.write(y, x, _get_capped_cell(cell["value"]), bold)
                else:
                    worksheet.write(y, x, _get_capped_cell(cell["value"]))
            y += 1
