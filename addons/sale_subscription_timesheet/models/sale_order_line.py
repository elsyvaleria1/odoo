from typing import Self

from odoo import api, models
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog
from odoo.tools import groupby

_debug = DebugLog(__name__)


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    def _is_postpaid_line(self) -> bool:
        self.check_singleton()
        return bool(
            (
                self.product_id.service_policy == "delivered_timesheet"
                and self.qty_transferred_method == "timesheet"
            )
            or super()._is_postpaid_line()
        )

    def _filtered_timesheet_subscription_lines(self) -> Self:
        return self.filtered(
            lambda sol: (
                sol.recurring_invoice and sol.qty_transferred_method == "timesheet"
            )
        )

    @api.depends("timesheet_ids", "next_invoice_date")
    def _compute_qty_transferred(self):
        timesheet_lines = self._filtered_timesheet_subscription_lines()
        res = super(SaleOrderLine, self - timesheet_lines)._compute_qty_transferred()

        for so, lines in groupby(timesheet_lines, lambda sol: sol.order_id):
            lines_by_timesheet = sum(lines, self.env["sale.order.line"])
            domain = Domain(
                lines_by_timesheet._timesheet_compute_delivered_quantity_domain()
            )
            refund_account_moves = so.invoice_ids.filtered(
                lambda am: am.state == "posted" and am.move_type == "out_refund"
            ).reversed_entry_id
            timesheet_domain = Domain("timesheet_invoice_id", "=", False) | Domain(
                "timesheet_invoice_id.state", "=", "cancel"
            )
            if refund_account_moves:
                _debug.logic(
                    "timesheet_domain_widened_for_refunds",
                    order=so,
                    refunded_moves=refund_account_moves,
                )
                credited_timesheet_domain = Domain(
                    "timesheet_invoice_id.state", "=", "posted"
                ) & Domain("timesheet_invoice_id", "in", refund_account_moves.ids)
                timesheet_domain |= credited_timesheet_domain
            # Shortcut to allow computing the domain for a bunch of lines without using _get_deferred_date that does not work in batch.
            # Side effect: It won't work for the first period if the invoice cron never run. (the next invoice date has never been incremented)
            domain = Domain.AND(
                [
                    domain,
                    timesheet_domain,
                    Domain("date", ">=", so.last_invoice_date or so.start_date),
                    Domain("date", "<", so.next_invoice_date),
                ]
            )
            _debug.perf.count(
                "timesheet_qty_by_analytic",
                order=so,
                lines=len(lines_by_timesheet),
                from_date=so.last_invoice_date or so.start_date,
                to_date=so.next_invoice_date,
            )
            mapping = lines_by_timesheet.sudo()._get_qty_delivered_by_analytic(domain)
            for line in lines:
                line.qty_transferred = mapping[line.id]
        return res

    def _prepare_qty_transferred(self):
        timesheet_lines = self._filtered_timesheet_subscription_lines()
        delivered_qties = super(
            SaleOrderLine, self - timesheet_lines
        )._prepare_qty_transferred()

        for so, lines in groupby(timesheet_lines, lambda sol: sol.order_id):
            lines_by_timesheet = sum(lines, self.env["sale.order.line"])
            domain = Domain(
                lines_by_timesheet._timesheet_compute_delivered_quantity_domain()
            )
            refund_account_moves = so.invoice_ids.filtered(
                lambda am: am.state == "posted" and am.move_type == "out_refund"
            ).reversed_entry_id
            timesheet_domain = Domain("timesheet_invoice_id", "=", False) | Domain(
                "timesheet_invoice_id.state", "=", "cancel"
            )
            if refund_account_moves:
                _debug.logic(
                    "timesheet_domain_widened_for_refunds",
                    order=so,
                    refunded_moves=refund_account_moves,
                )
                credited_timesheet_domain = Domain(
                    "timesheet_invoice_id.state", "=", "posted"
                ) & Domain("timesheet_invoice_id", "in", refund_account_moves.ids)
                timesheet_domain |= credited_timesheet_domain
            # Shortcut to allow computing the domain for a bunch of lines without using _get_deferred_date that does not work in batch.
            # Side effect: It won't work for the first period if the invoice cron never run. (the next invoice date has never been incremented)
            domain = Domain.AND(
                [
                    domain,
                    timesheet_domain,
                    Domain("date", ">=", so.last_invoice_date or so.start_date),
                    Domain("date", "<", so.next_invoice_date),
                ]
            )
            _debug.perf.count(
                "timesheet_qty_by_analytic",
                order=so,
                lines=len(lines_by_timesheet),
                from_date=so.last_invoice_date or so.start_date,
                to_date=so.next_invoice_date,
            )
            mapping = lines_by_timesheet.sudo()._get_qty_delivered_by_analytic(domain)
            for line in lines:
                delivered_qties[line] = mapping[line.id]
        return delivered_qties

    def _compute_display_name(self):
        subscriptions = self.filtered(lambda sol: sol.order_id.is_subscription)
        super(
            SaleOrderLine, subscriptions.with_context(skip_remaining_hours=True)
        )._compute_display_name()
        super(SaleOrderLine, self - subscriptions)._compute_display_name()

    def _compute_remaining_hours_available(self) -> None:
        subscription_lines = self.filtered(lambda sol: sol.order_id.is_subscription)
        super(
            SaleOrderLine, self - subscription_lines
        )._compute_remaining_hours_available()
        _debug.logic(
            "remaining_hours_hidden_for_subscriptions",
            lines=subscription_lines,
        )
        for line in subscription_lines:
            line.remaining_hours_available = False
