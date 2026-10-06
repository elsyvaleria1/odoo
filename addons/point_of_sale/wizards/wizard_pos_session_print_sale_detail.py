from odoo import fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WizardPosSessionPrintSaleDetail(models.TransientModel):
    _name = "wizard.pos.session.print.sale.detail"
    _description = "Point of Sale Daily Report"

    pos_session_id = fields.Many2one(
        comodel_name="pos.session",
        required=True,
    )

    def _prepare_report_params(self) -> dict:
        self.check_singleton()
        return {
            "date_start": False,
            "date_stop": False,
            "config_ids": self.pos_session_id.config_id.ids,
            "session_ids": self.pos_session_id.ids,
        }

    def action_print_report(self):
        self.check_singleton()
        _debug.lifecycle("daily_report_print", session=self.pos_session_id)
        return self.env.ref("point_of_sale.sale_details_report").report_action(
            [], data=self._prepare_report_params()
        )
