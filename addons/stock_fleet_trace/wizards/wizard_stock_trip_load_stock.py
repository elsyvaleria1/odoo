from odoo import fields, models
from odoo.exceptions import UserError


class WizardStockTripLoadStock(models.TransientModel):
    _name = "wizard.stock.trip.load.stock"
    _description = "Load Stock to Sell on a Trip"

    batch_id = fields.Many2one(
        comodel_name="stock.picking.batch",
        required=True,
        ondelete="cascade",
    )
    line_ids = fields.One2many(
        comodel_name="wizard.stock.trip.load.stock.line",
        inverse_name="wizard_id",
        string="Products",
    )

    def action_load(self) -> None:
        self.check_singleton()
        lines = self.line_ids.filtered(lambda line: line.quantity > 0)
        if not lines:
            raise UserError(self.env._("Say what the vehicle takes to sell."))
        self.batch_id._trip_load_free_stock(
            [(line.product_id, line.quantity) for line in lines]
        )


class WizardStockTripLoadStockLine(models.TransientModel):
    _name = "wizard.stock.trip.load.stock.line"
    _description = "Stock to Sell on a Trip"

    wizard_id = fields.Many2one(
        comodel_name="wizard.stock.trip.load.stock",
        required=True,
        ondelete="cascade",
    )
    product_id = fields.Many2one(
        comodel_name="product.product",
        required=True,
        domain="[('is_storable', '=', True)]",
    )
    uom_id = fields.Many2one(
        related="product_id.uom_id",
    )
    quantity = fields.Float(
        digits="Product Unit",
        required=True,
    )
