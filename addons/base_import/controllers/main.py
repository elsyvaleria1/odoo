from odoo import http
from odoo.exceptions import MissingError, UserError
from odoo.http import request


class ImportController(http.Controller):
    MAX_UPLOAD_SIZE = 64 * 1024 * 1024

    @http.route(
        "/base_import/set_file",
        methods=["POST"],
        type="http",
        auth="user",
        max_content_length=MAX_UPLOAD_SIZE,
    )
    def set_file(self, id=None, ufile=None):
        try:
            import_id = int(id)
        except (TypeError, ValueError) as exc:
            raise UserError(request.env._("Invalid import identifier.")) from exc

        files = request.httprequest.files.getlist("ufile")
        if not files:
            raise UserError(request.env._("No file was uploaded."))
        file = files[0]

        record = request.env["base_import.import"].browse(import_id).exists()
        if not record:
            raise MissingError(
                request.env._("This import does not exist or is no longer available.")
            )

        written = record.write(
            {
                "file": file.read(),
                "file_name": file.filename,
                "file_type": file.content_type,
            }
        )

        return request.prepare_json_response({"result": written})
