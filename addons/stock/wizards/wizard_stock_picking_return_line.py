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
        related="move_id.quantity",
        string="Move Quantity",
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
