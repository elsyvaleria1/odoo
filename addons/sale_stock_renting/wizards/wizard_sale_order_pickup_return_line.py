from markupsafe import Markup

from odoo import Command, api, fields, models
from odoo.api import ValuesType
from odoo.exceptions import ValidationError


class WizardSaleOrderPickupReturnLine(models.TransientModel):
    _inherit = "wizard.sale.order.pickup.return.line"

    def _prepare_wizard_line_vals(self, line, status) -> ValuesType:
        default_line_vals = super()._prepare_wizard_line_vals(line, status)

        default_line_vals.update(
            {
                "tracking": line.product_id.tracking,
            }
        )

        pickeable_lots = self.env["product.trace"]
        returnable_lots = self.env["product.trace"]
        reserved_lots = line.reserved_trace_ids
        pickedup_lots = line.pickedup_trace_ids
        returned_lots = line.returned_trace_ids

        if status == "pickup":
            if line.product_id.tracking == "serial":
                rentable_lots = self.env["product.trace"]._get_available_lots(
                    line.product_id, line.order_id.warehouse_id.lot_stock_id
                )
                rented_lots = line.product_id._get_unavailable_lots(
                    fields.Datetime.now(),
                    line.return_date,
                    ignored_soline_id=line.id,
                    warehouse_id=line.order_id.warehouse_id.id,
                )

                if pickedup_lots:
                    rented_lots += pickedup_lots

                if returned_lots:
                    """As returned lots are considered available, in case of partial pickup+return
                    We could pickup X, return X and then X would always be available for pickup
                    As this would bring problems of quantities and other unexpected behavior
                    We consider that returned serial numbers cannot be picked up again
                    for the same order_line."""
                    rented_lots += returned_lots

                pickeable_lots = rentable_lots - rented_lots

                reserved_lots &= pickeable_lots
                default_line_vals.update(
                    {
                        "qty_transferred": len(reserved_lots),
                    }
                )

            if line.product_id.is_storable:
                default_line_vals.update(
                    {
                        "qty_available": line.product_id.with_context(
                            from_date=max(
                                line.reservation_begin, fields.Datetime.now()
                            ),
                            to_date=line.return_date,
                            warehouse_id=line.order_id.warehouse_id.id,
                        ).qty_available,
                        "is_product_storable": True,
                    }
                )

            default_line_vals.update(
                {
                    "pickedup_trace_ids": [Command.set(reserved_lots.ids)],
                    "returned_trace_ids": [Command.set(returned_lots.ids)],
                    "pickeable_trace_ids": [Command.set(pickeable_lots.ids)],
                    "returnable_trace_ids": [Command.set(returnable_lots.ids)],
                }
            )
        elif status == "return":
            returnable_lots = pickedup_lots - returned_lots
            default_line_vals.update(
                {
                    "pickedup_trace_ids": [Command.set(pickedup_lots.ids)],
                    "returned_trace_ids": [Command.set(returnable_lots.ids)],
                    "pickeable_trace_ids": [Command.set(pickeable_lots.ids)],
                    "returnable_trace_ids": [Command.set(returnable_lots.ids)],
                }
            )

        return default_line_vals

    qty_available = fields.Float(
        string="Available",
        default=0.0,
    )
    is_product_storable = fields.Boolean(compute="_compute_is_product_storable")

    tracking = fields.Selection(related="product_id.tracking")

    pickeable_trace_ids = fields.Many2many(
        comodel_name="product.trace",
        relation="wizard_pickeable_serial",
        store=False,
    )
    returnable_trace_ids = fields.Many2many(
        comodel_name="product.trace",
        relation="wizard_returnable_serial",
        store=False,
    )
    pickedup_trace_ids = fields.Many2many(
        comodel_name="product.trace",
        relation="wizard_pickedup_serial",
        domain="[('id', 'in', pickeable_trace_ids)]",
    )
    returned_trace_ids = fields.Many2many(
        comodel_name="product.trace",
        relation="wizard_returned_serial",
        domain="[('id', 'in', returnable_trace_ids)]",
    )

    @api.depends("product_id")
    def _compute_is_product_storable(self) -> None:
        for line in self:
            line.is_product_storable = line.product_id and line.product_id.is_storable

    @api.onchange("pickedup_trace_ids")
    def _onchange_pickedup_trace_ids(self) -> None:
        self.qty_transferred = len(self.pickedup_trace_ids)

    @api.onchange("returned_trace_ids")
    def _onchange_returned_trace_ids(self) -> None:
        self.qty_returned = len(self.returned_trace_ids)

    @api.constrains("pickedup_trace_ids", "qty_transferred")
    def _check_pickup_tracking(self) -> None:
        for wizard_line in self:
            if wizard_line.status == "pickup" and wizard_line.tracking == "serial":
                if wizard_line.qty_transferred != len(wizard_line.pickedup_trace_ids):
                    raise ValidationError(
                        self.env._(
                            "Please specify the serial numbers picked up for the tracked products."
                        )
                    )

    @api.constrains("returned_trace_ids", "qty_returned")
    def _check_return_tracking(self) -> None:
        for wizard_line in self:
            if wizard_line.status == "return" and wizard_line.tracking == "serial":
                if wizard_line.qty_returned != len(wizard_line.returned_trace_ids):
                    raise ValidationError(
                        self.env._(
                            "Please specify the serial numbers returned for the tracked products."
                        )
                    )

    def _apply(self):
        serial_lines = self.filtered(lambda line: line.tracking == "serial")

        for line in serial_lines:
            sol = line.order_line_id
            if line.status == "pickup":
                pickedup_trace_ids = line.pickedup_trace_ids - sol.pickedup_trace_ids
                line.write(
                    {
                        "qty_transferred": len(pickedup_trace_ids),
                        "pickedup_trace_ids": [Command.set(pickedup_trace_ids.ids)],
                    }
                )
            elif line.status == "return":
                returned_trace_ids = line.returned_trace_ids - sol.returned_trace_ids
                line.write(
                    {
                        "qty_returned": len(returned_trace_ids),
                        "returned_trace_ids": [Command.set(returned_trace_ids.ids)],
                    }
                )

        msg = super()._apply()
        for line in serial_lines:
            sol = line.order_line_id
            if line.status == "pickup":
                sol.pickedup_trace_ids |= line.pickedup_trace_ids
            elif line.status == "return":
                sol.returned_trace_ids |= line.returned_trace_ids
        return msg

    def _generate_log_message(self):
        msg = ""
        for line in self:
            order_line = line.order_line_id
            diff, old_qty, new_qty = line._get_diff()
            if diff:
                msg += Markup("<li> %s") % (order_line.product_id.display_name)

                if old_qty > 0:
                    msg += Markup(": %s -> <b> %s </b> %s ") % (
                        old_qty,
                        new_qty,
                        order_line.product_uom_id.name,
                    )
                elif new_qty != 1 or order_line.product_qty > 1.0:
                    msg += ": %s %s " % (new_qty, order_line.product_uom_id.name)

                if line.status == "pickup" and line.pickedup_trace_ids:
                    msg += ": " + ", ".join(line.pickedup_trace_ids.mapped("name"))
                elif line.status == "return" and line.returned_trace_ids:
                    msg += ": " + ", ".join(line.returned_trace_ids.mapped("name"))

                msg += Markup("<br/>")
        return msg
