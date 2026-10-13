from odoo import fields, models


class StockPickingType(models.Model):
    """Configure automatic validation for delivered carrier shipments."""

    _inherit = "stock.picking.type"

    auto_validation_carrier_ids = fields.Many2many(
        comodel_name="delivery.carrier",
        string="Validate on Carrier Delivery",
        check_company=True,
        domain="[('tracking_provider', '!=', False)]",
        help="Automatically validate ready outgoing transfers when all their "
        "tracking numbers report delivery through one of these carriers. "
        "Normal validation checks still apply. Leave empty to validate manually.",
    )
