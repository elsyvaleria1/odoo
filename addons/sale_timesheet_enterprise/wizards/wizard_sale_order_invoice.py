from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

from odoo.addons.sale_timesheet_enterprise.models.sale_order_line import (
    DEFAULT_INVOICED_TIMESHEET,
)

_debug = DebugLog(__name__)


class WizardSaleOrderInvoice(models.TransientModel):
    _inherit = "wizard.sale.order.invoice"

    has_timer_running = fields.Boolean(
        export_string_translation=False,
        compute="_compute_has_timer_running",
    )

    @api.depends("date_start_invoice_timesheet", "date_end_invoice_timesheet")
    def _compute_has_timer_running(self) -> None:
        param_invoiced_timesheet = self.env.registry.settings.get(
            self.env, "sale.invoiced_timesheet", DEFAULT_INVOICED_TIMESHEET
        )
        if param_invoiced_timesheet == "approved":
            # Then no need to check if there is some timer running for the
            # timesheets linked to the SOs because we will just take the
            # validated ones and so no timer should be running for those ones.
            self.has_timer_running = False
            return
        Timesheet = self.env["account.analytic.line"]
        for wizard in self:
            timesheets = self.sudo()._get_timesheets()
            wizard.has_timer_running = (
                self.env["timer.timer"]
                .sudo()
                .search_count(
                    [
                        ("res_id", "in", timesheets.ids),
                        ("res_model", "=", Timesheet._name),
                    ],
                    limit=1,
                )
                > 0
            )

    def _get_timesheets(self):
        timesheet_domain = [
            ("project_id", "!=", False),
            ("order_id", "in", self.sale_order_ids.ids),
            ("validated", "=", False),
        ]
        if self.date_start_invoice_timesheet and self.date_end_invoice_timesheet:
            timesheet_domain += [
                ("date", "<=", self.date_end_invoice_timesheet),
                ("date", ">=", self.date_start_invoice_timesheet),
            ]
        return self.env["account.analytic.line"].search(timesheet_domain)

    def _create_invoices(self, sale_orders):
        if self.advance_payment_method == "delivered" and self.has_timer_running:
            _debug.lifecycle("running_timers_stopped_for_invoice", wizard=self)
            self.sudo()._get_timesheets()._stop_all_users_timer()
        return super()._create_invoices(sale_orders)
