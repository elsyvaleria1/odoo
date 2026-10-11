import re
from urllib.parse import quote

from werkzeug.exceptions import BadRequest

from odoo.http import STATIC_CACHE_LONG, request, route
from odoo.libs.debug_log import DebugLog
from odoo.tools import replace_exceptions

from odoo.addons.document.controllers.document import ShareRoute
from odoo.addons.spreadsheet.utils.json import extend_serialized_json

SPREADSHEET_RE = re.compile(r"\.osheet(\s?\(\d+\))?\.json$")

_debug = DebugLog(__name__)


class SpreadsheetShareRoute(ShareRoute):
    def _documents_render_public_view(self, document_sudo):
        if document_sudo.handler in ("spreadsheet", "frozen_spreadsheet"):
            return self._documents_render_portal_view(document_sudo)

        return super()._documents_render_public_view(document_sudo)

    def _documents_render_portal_view(self, document):
        if document.handler not in ("spreadsheet", "frozen_spreadsheet"):
            return super()._documents_render_portal_view(document)

        if document._contains_live_data():
            _debug.logic(
                "spreadsheet_portal_view_refused", document=document, reason="live_data"
            )
            return request.render("document_spreadsheet.documents_error_live_data")
        _debug.lifecycle(
            "spreadsheet_portal_view_rendered",
            document=document,
            frozen=document.handler == "frozen_spreadsheet",
        )

        return request.render(
            "spreadsheet.public_spreadsheet_layout",
            {
                "spreadsheet_name": document.name,
                "share": document,
                "is_frozen": document.handler == "frozen_spreadsheet",
                "session_info": request.env["ir.http"].session_info(),
                "props": {
                    "dataUrl": f"/documents/spreadsheet/{quote(document.access_token, safe='')}",
                    "downloadExcelUrl": document.excel_export
                    and f"/documents/content/{quote(document.access_token, safe='')}",
                },
            },
        )

    def _documents_content_stream(self, document_sudo):
        if document_sudo.handler == "frozen_spreadsheet":
            return request.env["ir.binary"]._get_stream_from_record(
                document_sudo, "excel_export"
            )
        elif document_sudo.handler == "spreadsheet":
            raise ValueError("non-frozen spreadsheets have no content")
        return super()._documents_content_stream(document_sudo)

    @route(
        "/documents/spreadsheet/<access_token>",
        type="http",
        auth="public",
        readonly=True,
    )
    def documents_spreadsheet(self, access_token):
        document_sudo = self._from_access_token(access_token, skip_log=True)
        if not document_sudo:
            _debug.logic("spreadsheet_public_data_not_found", reason="unknown_token")
            raise request.prepare_not_found_error()

        spreadsheet_data = document_sudo._get_spreadsheet_serialized_snapshot()
        serialized_revisions = ",".join(
            document_sudo._get_spreadsheet_serialized_revisions()
        )
        body = extend_serialized_json(
            spreadsheet_data, [("revisions", "[%s]" % serialized_revisions)]
        )
        _debug.pipeline(
            "spreadsheet_public_data_served",
            document=document_sudo,
            body_chars=len(body),
        )
        headers = [
            ("Content-Length", len(body)),
            ("Content-Type", "application/json; charset=utf-8"),
        ]
        return request.prepare_response(body, headers)

    def _documents_upload_post(self, document_sudo, vals):
        super()._documents_upload_post(document_sudo, vals)
        if _debug.logic.enabled:
            _debug.logic(
                "spreadsheet_upload_gate",
                document=document_sudo,
                name_matches=bool(
                    document_sudo.name and SPREADSHEET_RE.search(document_sudo.name)
                ),
                mimetype=document_sudo.mimetype,
            )
        if (
            document_sudo.name
            and SPREADSHEET_RE.search(document_sudo.name)
            and document_sudo.mimetype == "application/json"
        ):
            _debug.logic("spreadsheet_uploaded_as_osheet", document=document_sudo)
            if document_sudo.access_via_link == "edit":
                document_sudo._update_access_rights(
                    access_via_link="view", no_propagation=True
                )
            document_sudo.handler = "spreadsheet"
            document_sudo._check_spreadsheet_data()

    @route(
        [
            "/documents/display_thumbnail/<access_token>",
            "/documents/display_thumbnail/<access_token>/<int:width>x<int:height>",
        ],
        type="http",
        auth="public",
        readonly=True,
    )
    def documents_display_thumbnail(
        self, access_token, width="0", height="0", unique=""
    ):
        with replace_exceptions(ValueError, by=BadRequest):
            width = int(width)
            height = int(height)
        send_file_kwargs = {}
        if unique:
            send_file_kwargs["immutable"] = True
            send_file_kwargs["max_age"] = STATIC_CACHE_LONG
        spreadsheet_sudo = self._from_access_token(access_token, skip_log=True)
        return (
            request.env["ir.binary"]
            ._get_stream_image_from_record(
                spreadsheet_sudo, "display_thumbnail", width=width, height=height
            )
            .prepare_response(as_attachment=False, **send_file_kwargs)
        )
