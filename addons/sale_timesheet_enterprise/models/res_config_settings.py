from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

from odoo.addons.sale_timesheet_enterprise.models.sale_order_line import (
    DEFAULT_INVOICED_TIMESHEET,
)

_debug = DebugLog(__name__)


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    timesheet_show_rates = fields.Boolean(
        related="company_id.timesheet_show_rates",
        string="Billing Rate Indicators",
        readonly=False,
        help="Show the billing indicators on My Timesheets view",
    )
    timesheet_show_leaderboard = fields.Boolean(
        related="company_id.timesheet_show_leaderboard",
        string="Billing Rate Leaderboard",
        readonly=False,
        help="Show the leaderboard on My Timesheets view",
    )
    invoiced_timesheet = fields.Selection(
        selection=[
            ("all", "All recorded timesheets"),
            ("approved", "Validated timesheets only"),
        ],
        string="Timesheets Invoicing",
        default=DEFAULT_INVOICED_TIMESHEET,
        config_parameter="sale.invoiced_timesheet",
        help="With the 'all recorded timesheets' option, all timesheets will be invoiced without distinction, even if they haven't been validated."
        " Additionally, all timesheets will be accessible in your customers' portal. \n"
        "When you choose the 'validated timesheets only' option, only the validated timesheets will be invoiced and appear in your customers' portal.",
    )

    def set_values(self):
        old_value = self.env.registry.settings.get(
            self.env, "sale.invoiced_timesheet", False
        )
        if old_value and self.invoiced_timesheet != old_value:
            sale_order_lines = (
                self.env["sale.order.line"]
                .sudo()
                .search(
                    [
                        ("state", "=", "done"),
                        ("invoice_state", "in", ["no", "to do", "partial"]),
                        ("product_id.type", "=", "service"),
                        ("product_id.service_type", "=", "timesheet"),
                    ]
                )
            )

            _debug.pipeline(
                "invoiced_timesheet_policy_changed",
                old=old_value,
                new=self.invoiced_timesheet,
                lines=sale_order_lines,
            )
            if sale_order_lines:
                sale_order_lines._compute_qty_transferred()
                sale_order_lines._compute_invoice_state()
        return super().set_values()

    @api.onchange("timesheet_show_rates")
    def _onchange_timesheet_show_rates(self) -> None:
        if not self.timesheet_show_rates:
            _debug.logic("leaderboard_disabled", reason="rates_hidden")
            self.timesheet_show_leaderboard = False
