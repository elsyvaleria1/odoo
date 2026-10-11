import base64
import types
from urllib.parse import parse_qs, urlparse

from odoo import fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog
from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import loads as json_loads

_debug = DebugLog(__name__)


class WizardReportFormulaExportAttachmentFormat(models.TransientModel):
    _name = "wizard.report.formula.export.attachment.format"
    _description = "Export format for accounting's reports"

    name = fields.Char(required=True)
    fun_to_call = fields.Char(
        string="Function to Call",
        required=True,
    )
    fun_param = fields.Char(string="Function Parameter")
    export_wizard_id = fields.Many2one(
        comodel_name="wizard.report.formula.export.attachment",
        string="Parent Wizard",
        required=True,
        ondelete="cascade",
    )

    @_debug.perf.timed
    def apply_export(self, report_action):
        self.check_singleton()

        _debug.logic(
            "export_action_kind",
            format=self,
            action_type=report_action.get("type"),
        )
        if report_action["type"] == "ir_actions_account_report_download":
            report_options = json_loads(report_action["data"]["options"])
            file_generator = report_action["data"]["file_generator"]
            report = self.export_wizard_id.report_id
            report_options["report_id"] = report.id
            export_result = report.dispatch_report_action(
                report_options, file_generator
            )

            file_content = (
                base64.encodebytes(export_result["file_content"])
                if isinstance(export_result["file_content"], bytes)
                else export_result["file_content"]
            )
            if isinstance(file_content, types.GeneratorType):
                file_content = base64.encodebytes(b"".join(file_content))
            file_name = f"{self.export_wizard_id.doc_name or self.export_wizard_id.report_id.name}.{export_result['file_type']}"
            mimetype = self.export_wizard_id.report_id.get_export_mime_type(
                export_result["file_type"]
            )
            _debug.pipeline(
                "export_file_generated",
                report=report,
                file_generator=file_generator,
                file_type=export_result.get("file_type"),
                mimetype=mimetype,
            )

        elif report_action["type"] == "ir.actions.act_url":
            report_options = self.env.context.get(
                "account_report_generation_options", {}
            )
            query_params = parse_qs(urlparse(report_action["url"]).query)
            model = query_params["model"][0]
            model_id = int(query_params["id"][0])
            wizard = self.env[model].browse(model_id)
            file_name = wizard[query_params["filename_field"][0]]
            file_content = wizard[query_params["field"][0]]
            mimetype = self.env["report.formula"].get_export_mime_type(
                file_name.split(".")[-1]
            )

        else:
            raise UserError(
                self.env._("One of the formats chosen can not be exported in the DMS")
            )

        return self._prepare_attachment_vals(
            file_name, file_content, mimetype, report_options
        )

    def _prepare_attachment_vals(
        self, file_name, file_content, mimetype, log_options_dict
    ):
        self.check_singleton()
        return {
            "name": file_name,
            "company_id": self.env.company.id,
            "datas": file_content,
            "mimetype": mimetype,
            "description": json_dumps(log_options_dict),
        }
