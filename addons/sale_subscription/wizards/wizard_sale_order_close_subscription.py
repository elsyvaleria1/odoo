from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WizardSaleOrderCloseSubscription(models.TransientModel):
    _name = "wizard.sale.order.close.subscription"
    _description = "Subscription Close Reason Wizard"

    close_reason_id = fields.Many2one(
        comodel_name="sale.order.close.reason",
        required=True,
    )

    @api.model
    def new(self, values=None, origin=None, ref=None):
        sale_order = self.env["sale.order"].browse(self.env.context.get("active_id"))
        invoice_free = not any(
            state in ["draft", "posted"]
            for state in sale_order.line_ids.sudo().invoice_line_ids.mapped(
                "parent_state"
            )
        )
        invoice_free = invoice_free and not self.env["account.move.line"].sudo().search(
            [
                ("subscription_id", "=", sale_order.id),
                ("move_type", "=", "out_invoice"),
                ("parent_state", "in", ["draft", "posted"]),
            ],
            limit=1,
        )
        if invoice_free:
            _debug.logic("close_reason_wizard_refused", wizard=self)
            raise ValidationError(
                self.env._(
                    """You can not churn a contract that has not been invoiced. Please cancel the contract instead."""
                )
            )
        return super().new(values=values, origin=origin, ref=ref)

    def set_close(self):
        self.check_singleton()
        sale_order = self.env["sale.order"].browse(self.env.context.get("active_id"))
        sale_order.close_reason_id = self.close_reason_id
        sale_order.set_close(close_reason_id=self.close_reason_id.id)
