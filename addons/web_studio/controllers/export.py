import io
import logging
import zipfile

from werkzeug.exceptions import Forbidden, InternalServerError, NotFound

from odoo.http import (
    Controller,
    prepare_content_disposition_header,
    request,
    route,
    serialize_exception,
)

from .export_utils import StudioExportSerializer

_logger = logging.getLogger(__name__)


class StudioExporter(Controller):
    @route("/web_studio/export", type="http", auth="user")
    def export(self, token, active_id):
        if not self.env.is_admin():
            raise Forbidden

        module = self.env["ir.module.module"].get_or_create_studio_module()
        wizard_id = int(active_id)
        wizard = (
            self.env["wizard.ir.module.module.export.customization"]
            .browse(wizard_id)
            .exists()
        )
        if not wizard:
            raise NotFound

        try:
            export_info = wizard.get_export_info()
            content = self.generate_archive(module, export_info)
            return request.prepare_response(
                content,
                headers=[
                    (
                        "Content-Disposition",
                        prepare_content_disposition_header("customizations.zip"),
                    ),
                    ("Content-Type", "application/zip"),
                    ("Content-Length", len(content)),
                ],
            )
        except Exception as e:
            _logger.warning(
                "Error while generating studio export %s", module.name, exc_info=True
            )
            se = serialize_exception(e)
            error = {"code": 0, "message": "Odoo Server Error", "data": se}
            res = request.prepare_json_response(error, status=500)
            raise InternalServerError(response=res) from e

    def generate_archive(self, module, export_info):
        with io.BytesIO() as f:
            with zipfile.ZipFile(f, "w", zipfile.ZIP_STORED) as archive:
                for filename, content in self.generate_module_files(
                    module, export_info
                ):
                    archive.writestr(module.name + "/" + filename, content)
            return f.getvalue()

    def generate_module_files(self, module, export_info):
        yield from StudioExportSerializer(self.env, module, export_info).serialize()
