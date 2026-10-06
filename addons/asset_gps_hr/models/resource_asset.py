from odoo import fields, models


class ResourceAsset(models.Model):
    _inherit = "resource.asset"

    fuel_cost_per_km = fields.Monetary(
        help="Fuel cost billed per kilometer driven outside work hours. Used "
        "by the Vehicle Trip Report to compute the amount charged to the "
        "operator for out-of-hours use of this vehicle."
    )
