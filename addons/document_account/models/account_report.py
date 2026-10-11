from odoo import models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class AccountReport(models.Model):
    _inherit = "report.formula"

    def _init_options_buttons(self, options, previous_options) -> None:
        super()._init_options_buttons(options, previous_options)
        options["buttons"].append(
            {
                "name": self.env._("Copy to Documents"),
                "sequence": 100,
                "action": "open_report_export_wizard",
            }
        )

    def open_report_export_wizard(self, options):
        self.check_singleton()
        new_context = {
            **self.env.context,
            "account_report_generation_options": options,
            "default_report_id": self.id,
        }
        view_id = self.env.ref("account.view_report_export_wizard").id

        new_wizard = (
            self.with_context(new_context)
            .env["wizard.report.formula.export.attachment"]
            .create({"report_id": self.id})
        )
        _debug.lifecycle("report_export_wizard_opened", report=self, wizard=new_wizard)

        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Export"),
            "view_mode": "form",
            "res_model": "wizard.report.formula.export.attachment",
            "res_id": new_wizard.id,
            "target": "new",
            "views": [[view_id, "form"]],
            "context": new_context,
        }
