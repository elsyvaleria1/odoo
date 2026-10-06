from odoo import api, fields, models


class ProductTrace(models.Model):
    _inherit = "product.trace"

    fuel_cost_per_km = fields.Monetary(
        related="asset_id.fuel_cost_per_km",
        readonly=False,
    )

    @api.model
    def _asset_ledger_field_map(self):
        return super()._asset_ledger_field_map() | {
            "fuel_cost_per_km": "fuel_cost_per_km"
        }
