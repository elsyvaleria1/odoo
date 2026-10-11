from odoo import api, models
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog

from odoo.addons.sale_timesheet_enterprise.models.sale_order_line import (
    DEFAULT_INVOICED_TIMESHEET,
)

_debug = DebugLog(__name__)


class AccountAnalyticLine(models.Model):
    _inherit = "account.analytic.line"

    def _compute_display_timer(self) -> None:
        invoiced_timesheets = self.filtered("timesheet_invoice_id")
        invoiced_timesheets.display_timer = False
        super(AccountAnalyticLine, self - invoiced_timesheets)._compute_display_timer()

    @api.depends("validated")
    def _compute_so_line(self) -> None:
        updatable_timesheets = self.filtered(lambda t: t._is_updatable_timesheet())
        super(AccountAnalyticLine, updatable_timesheets)._compute_so_line()

    @api.model
    def grid_update_cell(self, domain, measure_field_name, value):
        return super().grid_update_cell(
            Domain.AND([domain, [("timesheet_invoice_id", "=", False)]]),
            measure_field_name,
            value,
        )

    def _is_updatable_timesheet(self) -> bool:
        _debug.logic("timesheet_updatable", line=self, validated=self.validated)
        return bool(super()._is_updatable_timesheet() and not self.validated)

    def _get_domain_last_timesheet(self):
        domain = super()._get_domain_last_timesheet()
        return Domain.AND(
            [
                domain,
                [
                    "|",
                    ("timesheet_invoice_id", "=", False),
                    ("timesheet_invoice_id.state", "=", "cancel"),
                ],
            ]
        )

    def _is_timer_hidden(self) -> bool:
        self.check_singleton()
        _debug.logic("timer_hidden", line=self, invoice=self.timesheet_invoice_id)
        return bool(super()._is_timer_hidden() or self.timesheet_invoice_id)

    def _timesheet_get_portal_domain(self):
        domain = super()._timesheet_get_portal_domain()
        param_invoiced_timesheet = self.env.registry.settings.get(
            self.env, "sale.invoiced_timesheet", DEFAULT_INVOICED_TIMESHEET
        )
        _debug.logic(
            "portal_timesheets_narrowed", by=param_invoiced_timesheet or "default"
        )
        if param_invoiced_timesheet == "approved":
            domain = Domain.AND([domain, [("validated", "=", True)]])
        return domain

    def _compute_can_validate(self):
        billed_lines = self.filtered(lambda l: l.validated and not l._is_not_billed())
        _debug.logic("validate_blocked_by_invoice", lines=billed_lines)
        for line in billed_lines:
            line.user_can_validate = False
        self -= billed_lines
        return super()._compute_can_validate()

    def action_invalidate_timesheet(self):
        invoice_validated_timesheets = self.filtered(lambda l: not l._is_not_billed())
        _debug.logic(
            "invalidate_skips_billed",
            requested=self,
            billed=invoice_validated_timesheets,
        )
        self -= invoice_validated_timesheets
        return super().action_invalidate_timesheet()

    def _get_timesheets_to_merge(self):
        res = super()._get_timesheets_to_merge()
        _debug.logic("merge_candidates_narrowed", candidates=res)
        return res.filtered(
            lambda line: (
                not line.timesheet_invoice_id
                or line.timesheet_invoice_id.state != "posted"
            )
        )
