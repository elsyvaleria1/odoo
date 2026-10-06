from odoo import fields, models


class StockLocation(models.Model):
    _inherit = "stock.location"

    deployed_location = fields.Boolean(
        default=False,
        tracking=True,
        help="Check this box if this location represents deployed/operational assets in use",
    )

    _check_location_flags_exclusive = models.Constraint(
        "CHECK(NOT (deployed_location AND maintenance_location))",
        "A location cannot be both a deployed location and a maintenance location.",
    )
