from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WizardReportFormulaExportAttachment(models.TransientModel):
    _name = "wizard.report.formula.export.attachment"
    _description = "Export wizard for accounting's reports"

    export_format_ids = fields.Many2many(
        comodel_name="wizard.report.formula.export.attachment.format",
        relation="dms_acc_rep_export_wizard_format_rel",
        string="Export to",
    )
    report_id = fields.Many2one(
        comodel_name="report.formula",
        string="Parent Report Id",
        required=True,
    )
    doc_name = fields.Char(
        string="Documents Name",
        help="Name to give to the generated documents.",
    )

    @api.model_create_multi
    @_debug.perf.timed
    def create(self, vals_list):
        if _debug.lifecycle.enabled:
            _debug.lifecycle(
                "create",
                model=self._name,
                count=len(vals_list),
                fields=sorted({key for vals in vals_list for key in vals}),
            )
        wizards = super().create(vals_list)
        for wizard in wizards:
            wizard.doc_name = wizard.report_id.name

            for button_dict in self.env.context.get(
                "account_report_generation_options", {}
            ).get("buttons", []):
                if button_dict.get("file_export_type"):
                    self.env["wizard.report.formula.export.attachment.format"].create(
                        {
                            "name": button_dict["file_export_type"],
                            "fun_to_call": button_dict["action"],
                            "fun_param": button_dict.get("action_param"),
                            "export_wizard_id": wizard.id,
                        }
                    )
        if _debug.pipeline.enabled:
            _debug.pipeline(
                "export_formats_created",
                wizards=wizards,
                formats_per_wizard=sum(
                    1
                    for button_dict in self.env.context.get(
                        "account_report_generation_options", {}
                    ).get("buttons", [])
                    if button_dict.get("file_export_type")
                ),
            )
        return wizards

    def export_report(self):
        self.check_singleton()
        created_attachments = self.env["ir.attachment"]
        for vals in self._get_attachments_to_save():
            created_attachments |= self.env["ir.attachment"].create(vals)
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Generated Documents"),
            "view_mode": "kanban,form",
            "res_model": "ir.attachment",
            "domain": [("id", "in", created_attachments.ids)],
        }

    def _get_attachments_to_save(self):
        self.check_singleton()
        to_create_attachments = []
        report_options = self.env.context["account_report_generation_options"]
        for format in self.export_format_ids:
            report_action = self.report_id.dispatch_report_action(
                options={**report_options, "report_id": self.report_id.id},
                action=format.fun_to_call,
                action_param=format.fun_param or None,
            )
            to_create_attachments.append(format.apply_export(report_action))

        return to_create_attachments
