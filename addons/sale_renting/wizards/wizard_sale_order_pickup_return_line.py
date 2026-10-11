from markupsafe import Markup

from odoo import api, fields, models
from odoo.api import ValuesType
from odoo.exceptions import ValidationError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WizardSaleOrderPickupReturnLine(models.TransientModel):
    _name = "wizard.sale.order.pickup.return.line"
    _description = "RentalOrderLine transient representation"

    @api.model
    def _prepare_wizard_line_vals(self, line, status) -> ValuesType:
        return {
            "order_line_id": line.id,
            "product_id": line.product_id.id,
            "qty_reserved": line.product_qty,
            "qty_transferred": line.qty_transferred
            if status == "return"
            else line.product_qty - line.qty_transferred,
            "qty_returned": line.qty_returned
            if status == "pickup"
            else line.qty_transferred - line.qty_returned,
        }

    rental_order_wizard_id = fields.Many2one(
        comodel_name="wizard.sale.order.pickup.return",
        required=True,
        ondelete="cascade",
    )
    status = fields.Selection(related="rental_order_wizard_id.status")

    order_line_id = fields.Many2one(
        comodel_name="sale.order.line",
        required=True,
        ondelete="cascade",
    )
    product_id = fields.Many2one(
        comodel_name="product.product",
        required=True,
        ondelete="cascade",
    )
    qty_reserved = fields.Float(string="Reserved")
    qty_transferred = fields.Float(string="Picked-up")
    qty_returned = fields.Float(string="Returned")

    @api.constrains("qty_returned", "qty_transferred")
    def _check_returned_quantity(self) -> None:
        for wizard_line in self:
            total_qty_returned = (
                wizard_line.qty_returned + wizard_line.order_line_id.qty_returned
            )
            if (
                wizard_line.status == "return"
                and total_qty_returned > wizard_line.qty_transferred
            ):
                _debug.logic(
                    "return_refused",
                    line=wizard_line.order_line_id,
                    returned=total_qty_returned,
                    picked_up=wizard_line.qty_transferred,
                )
                raise ValidationError(
                    self.env._("You can't return more than what's been picked-up.")
                )

    def _apply(self):
        msg = self._generate_log_message()
        for wizard_line in self:
            order_line = wizard_line.order_line_id
            if wizard_line.status == "pickup" and wizard_line.qty_transferred > 0:
                delivered_qty = order_line.qty_transferred + wizard_line.qty_transferred
                vals = {"qty_transferred": delivered_qty}
                if delivered_qty > order_line.product_qty:
                    vals["product_qty"] = delivered_qty
                _debug.lifecycle(
                    "rental_picked_up",
                    line=order_line,
                    quantity=wizard_line.qty_transferred,
                )
                order_line.update(vals)

            elif wizard_line.status == "return" and wizard_line.qty_returned > 0:
                _debug.lifecycle(
                    "rental_returned",
                    line=order_line,
                    quantity=wizard_line.qty_returned,
                    late=wizard_line.rental_order_wizard_id.is_late,
                )
                if wizard_line.rental_order_wizard_id.is_late:
                    order_line._create_delay_line(wizard_line.qty_returned)

                order_line.update(
                    {"qty_returned": order_line.qty_returned + wizard_line.qty_returned}
                )
        return msg

    def _get_diff(self) -> tuple:
        self.check_singleton()
        order_line = self.order_line_id
        if self.status == "pickup":
            return (
                self.qty_transferred,
                order_line.qty_transferred,
                order_line.qty_transferred + self.qty_transferred,
            )
        else:
            return (
                self.qty_returned,
                order_line.qty_returned,
                order_line.qty_returned + self.qty_returned,
            )

    def _generate_log_message(self):
        msg = ""
        for line in self:
            order_line = line.order_line_id
            diff, old_qty, new_qty = line._get_diff()
            if diff:
                msg += Markup("<li> %s") % (order_line.product_id.display_name)

                if old_qty > 0:
                    msg += Markup(": %s -> <b> %s </b> %s <br/>") % (
                        old_qty,
                        new_qty,
                        order_line.product_uom_id.name,
                    )
                elif new_qty != 1 or order_line.product_qty > 1.0:
                    msg += Markup(": %s %s <br/>") % (
                        new_qty,
                        order_line.product_uom_id.name,
                    )
        return msg
