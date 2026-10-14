from odoo import Command, api, fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WizardStockPickingReturnLine(models.TransientModel):
    _name = "wizard.stock.picking.return.line"
    _rec_name = "product_id"
    _description = "Return Picking Line"

    product_id = fields.Many2one(
        comodel_name="product.product",
        required=True,
    )
    move_quantity = fields.Float(
        string="Returnable Quantity",
        digits="Product Unit",
        compute="_compute_move_quantity",
    )
    quantity = fields.Float(
        digits="Product Unit",
        default=1,
        required=True,
    )
    uom_id = fields.Many2one(
        comodel_name="uom.uom",
        string="Unit",
        compute="_compute_uom_id",
    )
    wizard_id = fields.Many2one(comodel_name="wizard.stock.picking.return")
    move_id = fields.Many2one(comodel_name="stock.move")

    @api.depends(
        "move_id.quantity",
        "move_id.returned_move_ids.state",
        "move_id.returned_move_ids.quantity",
        "move_id.returned_move_ids.product_uom_qty",
    )
    def _compute_move_quantity(self) -> None:
        for line in self:
            line.move_quantity = line._get_returnable_quantity()

    def _get_returnable_quantity(self) -> float:
        self.check_singleton()
        stock_move = self.move_id
        if (
            not stock_move
            or stock_move.state == "cancel"
            or stock_move.location_dest_usage == "inventory"
        ):
            return 0.0
        quantity = stock_move.quantity
        for returned in stock_move.returned_move_ids:
            if returned.state == "cancel":
                continue
            returned_qty = (
                returned.quantity
                if returned.state == "done"
                else returned.product_uom_qty
            )
            quantity -= returned.product_uom_id._get_quantity_in_unit(
                returned_qty,
                stock_move.product_uom_id,
                round=False,
            )
        return max(stock_move.product_uom_id.round(quantity), 0)

    @api.depends("move_id.product_uom_id", "product_id.uom_id")
    def _compute_uom_id(self) -> None:
        for line in self:
            line.uom_id = line.move_id.product_uom_id or line.product_id.uom_id

    def _prepare_move_default_values(self, new_picking):
        picking = new_picking or self.wizard_id.picking_id
        vals = {
            "product_id": self.product_id.id,
            "product_uom_qty": self.quantity,
            "product_uom_id": self.uom_id.id,
            "picking_id": picking.id,
            "state": "draft",
            "date": fields.Datetime.now(),
            "location_id": picking.location_id.id or self.move_id.location_dest_id.id,
            "location_dest_id": picking.location_dest_id.id
            or self.move_id.location_id.id,
            "location_final_id": False,
            "picking_type_id": picking.picking_type_id.id,
            "warehouse_id": picking.picking_type_id.warehouse_id.id,
            "origin_returned_move_id": self.move_id.id,
            "procure_method": "make_to_stock",
            "reference_ids": self.wizard_id.picking_id.reference_ids.ids,
        }
        if picking.picking_type_id.code == "outgoing":
            vals["partner_id"] = picking.partner_id.id
        return vals

    def _process_line(self, new_picking) -> bool:
        self.check_singleton()
        if not self.uom_id.is_zero(self.quantity):
            vals = self._prepare_move_default_values(new_picking)

            if self.move_id:
                new_return_move = self.move_id.copy(vals)
                vals = {}
                move_orig_to_link = self.move_id.move_dest_ids.returned_move_ids
                move_orig_to_link |= self.move_id
                move_orig_to_link |= self.move_id.move_dest_ids.filtered(
                    lambda m: m.state != "cancel"
                ).move_orig_ids.filtered(lambda m: m.state != "cancel")
                move_dest_to_link = self.move_id.move_orig_ids.returned_move_ids
                move_dest_to_link |= (
                    self.move_id.move_orig_ids.returned_move_ids.move_orig_ids.filtered(
                        lambda m: m.state != "cancel"
                    ).move_dest_ids.filtered(lambda m: m.state != "cancel")
                )
                vals["move_orig_ids"] = [Command.link(m.id) for m in move_orig_to_link]
                vals["move_dest_ids"] = [Command.link(m.id) for m in move_dest_to_link]
                _debug.pipeline(
                    "return_line",
                    move=self.move_id.id,
                    return_move=new_return_move.id,
                    quantity=self.quantity,
                    orig=move_orig_to_link,
                    dest=move_dest_to_link,
                )
                new_return_move.write(vals)
            else:
                _debug.pipeline(
                    "return_line_without_move",
                    product=self.product_id.id,
                    quantity=self.quantity,
                )
                self.env["stock.move"].create(vals)
            return True
        return False
