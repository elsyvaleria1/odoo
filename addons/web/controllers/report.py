import io
import logging
import zipfile
from typing import Any
from urllib.parse import parse_qs, urlsplit

from odoo import http
from odoo.exceptions import AccessError
from odoo.http import (
    BadRequest,
    InternalServerError,
    Response,
    prepare_content_disposition_header,
    request,
)
from odoo.libs.debug_log import DebugLog
from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import loads as json_loads
from odoo.tools.authority_keys import strip_authority_keys
from odoo.tools.misc import html_escape
from odoo.tools.safe_eval import safe_eval, time

from .utils import parse_id_list

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)

_MAX_BARCODE_DIM = 10_000

_MAX_BARCODE_VALUE_LEN = 4096


_RENDERERS = {
    "html": ("_render_qweb_html", "text/html; charset=utf-8"),
    "pdf": ("_render_qweb_pdf", "application/pdf"),
    "text": ("_render_qweb_text", "text/plain; charset=utf-8"),
}

_DOWNLOAD_TYPES = {
    "qweb-pdf": ("pdf", "pdf"),
    "qweb-text": ("text", "txt"),
}


def _parse_docids(docids: str | None) -> list[int] | None:
    if not docids:
        return None
    return parse_id_list(docids)


def _clamp_barcode_dimension(raw: Any, default: int) -> int:
    try:
        value = int(raw)
    except ValueError, TypeError:
        return default
    if value < 1:
        return default
    return min(value, _MAX_BARCODE_DIM)


class ReportController(http.Controller):
    @http.route(
        [
            "/report/<converter>/<reportname>",
            "/report/<converter>/<reportname>/<docids>",
        ],
        type="http",
        auth="user",
        website=True,
        readonly=True,
    )
    def report_routes(
        self,
        reportname: str,
        docids: str | None = None,
        converter: str | None = None,
        **data,
    ) -> Response:
        if _debug.lifecycle.enabled:
            _debug.lifecycle(
                "report_routes",
                report=reportname,
                converter=converter,
                docids=docids,
                data=sorted(data),
            )
        if converter not in _RENDERERS:
            _debug.logic(
                "report_converter_unsupported", report=reportname, converter=converter
            )
            raise BadRequest(description=f"Converter {converter!r} not supported.")
        render_method, content_type = _RENDERERS[converter]
        self._check_report_loadable(reportname)
        report = request.env["ir.actions.report"]
        context = dict(request.env.context)

        doc_ids = _parse_docids(docids)
        if data.get("options"):
            data.update(json_loads(data.pop("options")))
            if _debug.logic.enabled:
                _debug.logic(
                    "report_options_merged", report=reportname, data=sorted(data)
                )
        if data.get("context"):
            data["context"] = strip_authority_keys(
                json_loads(data["context"]), door="report"
            )
            context.update(data["context"])
            if _debug.logic.enabled:
                _debug.logic(
                    "report_context_extended",
                    report=reportname,
                    keys=sorted(data["context"]),
                )
        _debug.pipeline(
            "report_render",
            report=reportname,
            converter=converter,
            docs=len(doc_ids or ()),
        )
        with _debug.perf(
            "report_render",
            cr=request.env.cr,
            report=reportname,
            converter=converter,
        ):
            body = getattr(report.with_context(context), render_method)(
                reportname, doc_ids, data=data
            )[0]
        _debug.perf.count(
            "report_body_size",
            report=reportname,
            converter=converter,
            size=len(body),
            unit="bytes" if isinstance(body, bytes) else "chars",
        )
        return request.prepare_response(body, headers=[("Content-Type", content_type)])

    @http.route(
        [
            "/report/barcode",
            "/report/barcode/<barcode_type>/<path:value>",
        ],
        type="http",
        auth="public",
        readonly=True,
    )
    def report_barcode(self, barcode_type: str, value: str, **kwargs) -> Response:
        if _debug.lifecycle.enabled:
            _debug.lifecycle(
                "report_barcode",
                barcode_type=barcode_type,
                value_len=len(value) if value is not None else None,
                kwargs=sorted(kwargs),
            )
        if value is not None and len(value) > _MAX_BARCODE_VALUE_LEN:
            _debug.logic("barcode_value_too_long", barcode_type=barcode_type)
            raise BadRequest("Barcode value is too long.")
        if "width" in kwargs:
            kwargs["width"] = _clamp_barcode_dimension(kwargs["width"], 600)
        if "height" in kwargs:
            kwargs["height"] = _clamp_barcode_dimension(kwargs["height"], 100)
        try:
            with _debug.perf(
                "barcode_prepare", cr=request.env.cr, barcode_type=barcode_type
            ):
                barcode = request.env["ir.actions.report"].prepare_barcode(
                    barcode_type, value, **kwargs
                )
        except (ValueError, AttributeError, KeyError) as exc:
            _debug.logic(
                "barcode_convert_failed",
                barcode_type=barcode_type,
                error=type(exc).__name__,
            )
            raise BadRequest("Cannot convert into barcode.") from None
        _debug.perf.count(
            "barcode_png_size", barcode_type=barcode_type, bytes=len(barcode)
        )

        return request.prepare_response(
            barcode,
            headers=[
                ("Content-Type", "image/png"),
                (
                    "Cache-Control",
                    f"public, max-age={http.STATIC_CACHE_LONG}, immutable",
                ),
            ],
        )

    @http.route(["/report/download"], type="http", auth="user")
    def report_download(
        self, data: str, context: str | None = None, **_kwargs
    ) -> Response:
        reportname = "???"
        try:
            url, type_ = json_loads(data)[:2]
            _debug.lifecycle(
                "report_download",
                report_type=type_,
                url=url,
                has_context=context is not None,
            )
            if type_ not in _DOWNLOAD_TYPES:
                _debug.logic("report_download_type_unsupported", report_type=type_)
                raise BadRequest(description=f"Report type {type_!r} not supported.")
            converter, extension = _DOWNLOAD_TYPES[type_]
            reportname, docids, query = self._parse_report_download_url(url, converter)
            _debug.pipeline(
                "report_download_route",
                report=reportname,
                converter=converter,
                docids=docids,
                via="docids" if docids else "query_string",
            )
            if docids:
                if converter == "pdf" and (
                    zipped := self._report_download_per_record(
                        reportname, docids, context
                    )
                ):
                    return zipped
                response = self.report_routes(
                    reportname, docids=docids, converter=converter, context=context
                )
            else:
                if "context" in query:
                    context = json_dumps(
                        {
                            **json_loads(context or "{}"),
                            **json_loads(query.pop("context")),
                        }
                    )
                response = self.report_routes(
                    reportname, converter=converter, context=context, **query
                )
            filename = self._get_report_download_name(reportname, docids, extension)
            response.headers.add(
                "Content-Disposition", prepare_content_disposition_header(filename)
            )
            _debug.pipeline(
                "report_download_attachment", report=reportname, filename=filename
            )
            return response
        except Exception as e:
            _debug.logic(
                "report_download_failed",
                report=reportname,
                error=type(e).__name__,
                status=500,
            )
            _logger.warning(
                "Error while generating report %s", reportname, exc_info=True
            )
            se = http.serialize_exception(e)
            error = {"code": 0, "message": "Odoo Server Error", "data": se}
            res = request.prepare_response(html_escape(json_dumps(error)), status=500)
            raise InternalServerError(response=res) from e

    def _parse_report_download_url(
        self, url: str, converter: str
    ) -> tuple[str, str | None, dict[str, str]]:
        pattern = f"/report/{converter}/"
        _, _, after_pattern = url.partition(pattern)
        if not after_pattern:
            _debug.logic("report_download_url_mismatch", pattern=pattern)
            raise BadRequest(
                description=f"URL does not match expected pattern {pattern!r}."
            )
        reportname, _, docids = after_pattern.split("?")[0].partition("/")
        query = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
        return reportname, docids or None, query

    def _get_report_download_name(
        self, reportname: str, docids: str | None, extension: str
    ) -> str:
        report = request.env["ir.actions.report"]._get_report_from_name(reportname)
        if docids and report.print_report_name:
            records = request.env[report.model].browse(_parse_docids(docids))
            if len(records) == 1:
                name = safe_eval(
                    report.print_report_name, {"object": records, "time": time}
                )
                _debug.logic("report_download_print_name", report=reportname, name=name)
                return f"{name}.{extension}"
        return f"{report.name}.{extension}"

    def _get_report_record_file_stem(self, report: Any, record: Any) -> str:
        if report.print_report_name:
            name = safe_eval(report.print_report_name, {"object": record, "time": time})
        else:
            name = f"{report.name} - {record.display_name}"
        return str(name).replace("/", "_").replace("\\", "_")

    def _check_report_loadable(self, reportname: str) -> None:
        report = request.env["ir.actions.report"]._get_report_from_name(reportname)
        if not report:
            _debug.logic("report_not_found", report=reportname)
            raise request.prepare_not_found_error()
        try:
            report.with_env(request.env)._check_access_to_load()
        except AccessError:
            _debug.logic("report_load_refused", report=reportname, uid=request.env.uid)
            raise request.prepare_not_found_error() from None

    def _report_download_per_record(
        self, reportname: str, docids: str, context: str | None
    ) -> Response | None:
        report = request.env["ir.actions.report"]._get_report_from_name(reportname)
        res_ids = list(dict.fromkeys(_parse_docids(docids) or ()))
        if len(res_ids) < 2 or not report._download_splits_per_record():
            return None
        self._check_report_loadable(reportname)
        render_context = dict(request.env.context)
        if context:
            render_context.update(
                strip_authority_keys(json_loads(context), door="report")
            )
        with _debug.perf("report_render_per_record", report=reportname):
            rendered = (
                request.env["ir.actions.report"]
                .with_context(render_context)
                ._render_qweb_pdf_per_record(reportname, res_ids)
            )
        records = request.env[report.model].browse(
            [res_id for res_id in res_ids if res_id in rendered]
        )
        _debug.pipeline(
            "report_download_per_record",
            report=reportname,
            rendered=len(records),
            requested=len(res_ids),
        )
        if not records:
            return None
        files = []
        taken = set()
        for record in records:
            stem = name = self._get_report_record_file_stem(report, record)
            copy = 1
            while name in taken:
                copy += 1
                name = f"{stem} ({copy})"
            taken.add(name)
            files.append((f"{name}.pdf", rendered[record.id][0]))
        if len(files) == 1:
            filename, content = files[0]
            content_type = "application/pdf"
        else:
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
                for name, file_content in files:
                    archive.writestr(name, file_content)
            filename, content = f"{report.name}.zip", buffer.getvalue()
            content_type = "application/zip"
        return request.prepare_response(
            content,
            headers=[
                ("Content-Type", content_type),
                ("Content-Disposition", prepare_content_disposition_header(filename)),
            ],
        )
