from typing import Self

from odoo import api, fields, models
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog

from odoo.addons.sale_timesheet_enterprise.models.sale_order_line import (
    DEFAULT_INVOICED_TIMESHEET,
)

_debug = DebugLog(__name__)


class AccountAnalyticLine(models.Model):
    _inherit = "account.analytic.line"

    display_sol = fields.Boolean(
        export_string_translation=False,
        compute="_compute_display_sol",
    )

    @api.depends("helpdesk_ticket_id")
    def _compute_commercial_partner_id(self) -> None:
        timesheets_with_ticket = self.filtered("helpdesk_ticket_id")
        super(
            AccountAnalyticLine, self - timesheets_with_ticket
        )._compute_commercial_partner_id()
        for line in timesheets_with_ticket:
            line.commercial_partner_id = line.helpdesk_ticket_id.commercial_partner_id

    @api.depends("helpdesk_ticket_id", "helpdesk_ticket_id.use_helpdesk_sale_timesheet")
    def _compute_display_sol(self) -> None:
        sale_project_ids = set(
            self.env["project.project"]._search(
                [("helpdesk_team.use_helpdesk_sale_timesheet", "=", True)]
            )
        )
        _debug.pipeline(
            "timesheet_display_sol",
            lines=self,
            # the project subquery is rebuilt on every call of this compute,
            # with nothing caching it across records or across calls
            billable_projects=len(sale_project_ids),
        )
        for line in self:
            if (
                line.project_id
                and not line.project_id.sudo().allow_billable
                and line.project_id.id not in sale_project_ids
            ):
                line.display_sol = False
            else:
                line.display_sol = (
                    not line.helpdesk_ticket_id
                    or line.helpdesk_ticket_id.use_helpdesk_sale_timesheet
                )

    @api.depends("helpdesk_ticket_id.sale_line_id")
    def _compute_so_line(self) -> None:
        _debug.pipeline("timesheet_so_line_compute", lines=self)
        non_billed_helpdesk_timesheets = self.filtered(
            lambda t: (
                not t.is_so_line_edited
                and t.helpdesk_ticket_id
                and t._is_not_billed()
                and not t.validated
            )
        )
        for timesheet in non_billed_helpdesk_timesheets:
            timesheet.so_line = (
                timesheet.project_id.allow_billable
                and timesheet.helpdesk_ticket_id.sale_line_id
            )
        super(
            AccountAnalyticLine, self - non_billed_helpdesk_timesheets
        )._compute_so_line()

    @api.depends("timesheet_invoice_id.state")
    def _compute_partner_id(self):
        if _debug.logic.enabled:
            _debug.logic(
                "timesheet_partner_compute",
                lines=self,
                # guarded because the filter is the method's own work: the
                # billed remainder is passed to no super() call and assigned
                # nothing, so this compute answers for a subset of `self`
                unassigned=self.filtered(lambda t: not t._is_not_billed()),
            )
        super(
            AccountAnalyticLine, self.filtered(lambda t: t._is_not_billed())
        )._compute_partner_id()

    def _get_portal_helpdesk_timesheet(self) -> Self:
        param_invoiced_timesheet = self.env.registry.settings.get(
            self.env, "sale.invoiced_timesheet", DEFAULT_INVOICED_TIMESHEET
        )
        if param_invoiced_timesheet == "approved":
            return self.filtered(lambda line: line.validated)
        return self

    def _can_timesheet_be_billed(self) -> bool:
        return (
            super()._can_timesheet_be_billed()
            or self.so_line == self.helpdesk_ticket_id.sale_line_id
        )

    def _timesheet_get_sale_domain(self, order_lines_ids, invoice_ids):
        domain = super()._timesheet_get_sale_domain(order_lines_ids, invoice_ids)
        if not invoice_ids:
            return domain

        return Domain.OR(
            [
                domain,
                [
                    "&",
                    "&",
                    ("task_id", "=", False),
                    ("helpdesk_ticket_id", "!=", False),
                    "&",
                    ("so_line", "in", order_lines_ids.ids),
                    ("timesheet_invoice_id", "=", False),
                ],
            ]
        )
