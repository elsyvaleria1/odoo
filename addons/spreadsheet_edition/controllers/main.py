from werkzeug.datastructures import FileStorage

from odoo import http
from odoo.http import Controller, prepare_content_disposition_header, request
from odoo.libs.debug_log import DebugLog
from odoo.libs.documents import mimetype_for
from odoo.libs.json import loads as json_loads

_debug = DebugLog(__name__)


class SpreadsheetController(Controller):
    @http.route(
        [
            "/spreadsheet/data/<string:res_model>/<int:res_id>",
            "/spreadsheet/data/<string:res_model>/<int:res_id>/<access_token>",
        ],
        type="http",
        auth="user",
        methods=["GET"],
    )
    def get_spreadsheet_data(self, res_model, res_id, access_token=None, **kw):  # noqa: E8539  redirect: passes the token on to the page or record check that opens it
        cids_str = request.cookies.get("cids", str(request.env.user.company_id.id))
        try:
            cids = [int(cid) for cid in cids_str.split("-")]
        except ValueError:
            _debug.logic("spreadsheet_data_cids_unparsable", cids=cids_str)
            cids = [request.env.user.company_id.id]
        if res_model not in request.env:
            _debug.logic(
                "spreadsheet_data_not_found", reason="unknown_model", model=res_model
            )
            raise request.prepare_not_found_error()
        spreadsheet = (
            request.env[res_model]
            .browse(res_id)
            .exists()
            .with_context(allowed_company_ids=cids)
        )
        if not spreadsheet:
            _debug.logic(
                "spreadsheet_data_not_found",
                reason="missing_record",
                model=res_model,
                res_id=res_id,
            )
            raise request.prepare_not_found_error()
        _debug.lifecycle(
            "spreadsheet_data_requested",
            records=spreadsheet,
            companies=len(cids),
            via_token=bool(access_token),
        )
        body = spreadsheet._get_serialized_spreadsheet_data_body(access_token)
        headers = [
            ("Content-Length", len(body)),
            ("Cache-Control", "no-store"),
            ("Content-Type", "application/json; charset=utf-8"),
        ]
        return request.prepare_response(body, headers)

    @http.route(
        "/spreadsheet/xlsx", type="http", auth="user", methods=["POST"], readonly=True
    )
    def get_xlsx_file(self, zip_name, files, **kw):
        files = (
            json_loads(files.read())
            if isinstance(files, FileStorage)
            else json_loads(files)
        )

        content = request.env["mixin.spreadsheet"]._zip_xslx_files(files)
        _debug.pipeline(
            "spreadsheet_xlsx_served",
            files=len(files),
            bytes=len(content),
        )
        headers = [
            ("Content-Length", len(content)),
            (
                "Content-Type",
                mimetype_for("xlsx"),
            ),
            ("X-Content-Type-Options", "nosniff"),
            ("Content-Disposition", prepare_content_disposition_header(zip_name)),
        ]

        return request.prepare_response(content, headers)
