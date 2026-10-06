from odoo import fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WizardStockPickingPrintLabel(models.TransientModel):
    _name = "wizard.stock.picking.print.label"
    _description = "Choose whether to print product or lot/sn labels"

    picking_ids = fields.Many2many(comodel_name="stock.picking")
    label_type = fields.Selection(
        selection=[("products", "Product Labels"), ("lots", "Lot/SN Labels")],
        string="Labels to print",
        default="products",
        required=True,
    )

    def process(self):
        if not self.picking_ids:
            return None
        _debug.logic(
            "label_type", label_type=self.label_type, pickings=self.picking_ids
        )
        if self.label_type == "products":
            return self.picking_ids.action_view_label_layout()
        view = self.env.ref("stock.lot_label_layout_form_picking")
        return {
            "name": self.env._("Choose Labels Layout"),
            "type": "ir.actions.act_window",
            "res_model": "wizard.stock.move.line.print.lot.label",
            "views": [(view.id, "form")],
            "target": "new",
            "context": {"default_move_line_ids": self.picking_ids.move_line_ids.ids},
        }
