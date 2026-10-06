from odoo import api, fields, models


class WizardSaleOrderPickupReturn(models.TransientModel):
    _inherit = "wizard.sale.order.pickup.return"

    has_tracked_lines = fields.Boolean(
        string="Has lines with tracked products",
        compute="_compute_has_tracked_lines",
    )

    has_lines_missing_stock = fields.Boolean(
        string="Has lines whose products have insufficient stock",
        compute="_compute_has_lines_missing_stock",
    )

    @api.depends("rental_wizard_line_ids")
    def _compute_has_tracked_lines(self) -> None:
        for wizard in self:
            wizard.has_tracked_lines = any(
                line.tracking == "serial" for line in wizard.rental_wizard_line_ids
            )

    @api.depends("rental_wizard_line_ids.qty_transferred")
    def _compute_has_lines_missing_stock(self) -> None:
        for wizard in self:
            wizard.has_lines_missing_stock = any(
                line.is_product_storable
                and line.status == "pickup"
                and line.qty_transferred > line.qty_available
                for line in wizard.rental_wizard_line_ids
            )
