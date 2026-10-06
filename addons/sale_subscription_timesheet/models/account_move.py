from datetime import timedelta

from odoo import models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    def _get_range_dates(self, order) -> tuple:
        """Return the start and end dates for the subscription
        order's period to link the timesheets that just lays in
        between this period.
        :param order: order in which the dates are to be returned
        :return: a start date and end date for the subscription period
        """
        start_date, end_date = super()._get_range_dates(order)
        if order.is_subscription and order.line_ids.product_id.filtered(
            lambda p: p._is_delivered_timesheet()
        ):
            _debug.logic(
                "timesheet_range_from_subscription_period",
                move=self,
                order=order,
                start=order.last_invoice_date,
                end=order.next_invoice_date,
            )
            return order.last_invoice_date, order.next_invoice_date + timedelta(days=-1)
        return start_date, end_date
