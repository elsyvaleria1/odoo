from typing import Self

from odoo import api, fields, models
from odoo.exceptions import AccessError
from odoo.libs.debug_log import DebugLog
from odoo.tools import is_html_empty

_debug = DebugLog(__name__)


class SaleOrderCloseReason(models.Model):
    _name = "sale.order.close.reason"
    _order = "sequence, id"
    _description = "Subscription Close Reason"

    name = fields.Char(
        string="Reason",
        translate=True,
        required=True,
    )
    sequence = fields.Integer(default=10)

    visible_in_portal = fields.Boolean(
        default=True,
        required=True,
    )
    retention_message = fields.Html(
        string="Message",
        translate=True,
        help="Try to prevent customers from leaving and closing their subscriptions, thanks to a catchy message and a call to action.",
    )
    retention_button_text = fields.Char(
        string="Button Text",
        translate=True,
    )
    retention_button_link = fields.Char(
        string="Button Link",
        translate=True,
    )
    empty_retention_message = fields.Boolean(compute="_compute_empty_retention_message")
    # protected reasons can't be deleted as they are used by odoo bot
    is_protected = fields.Boolean(default=False)

    @api.depends("retention_message")
    def _compute_empty_retention_message(self) -> None:
        for reason in self:
            reason.empty_retention_message = is_html_empty(reason.retention_message)

    def write(self, vals):
        vals.pop("is_protected", None)
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_close_reasons(self) -> None:
        for reason in self:
            if reason.is_protected:
                _debug.logic("close_reason_unlink_refused", reasons=self)
                raise AccessError(
                    self.env._(
                        'The reason: "%s" is here for good. It\'s essential for our subscription application like coffee is for a Monday morning!',
                        reason.name,
                    )
                )

    @api.model
    def _get_reopen_reasons(self) -> Self:
        # Only a subscription closed for want of payment reopens once paid: the
        # failed automatic renewal and the unpaid-invoice cron. One closed on
        # purpose, by the customer or a salesperson, stays closed.
        return self.browse(
            reason.id
            for xmlid in (
                "sale_subscription.close_reason_auto_close_limit_reached",
                "sale_subscription.close_reason_unpaid_subscription",
            )
            if (reason := self.env.ref(xmlid, raise_if_not_found=False))
        )
