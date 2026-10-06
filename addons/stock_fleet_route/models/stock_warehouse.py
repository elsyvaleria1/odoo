from odoo import fields, models


class StockWarehouse(models.Model):
    _inherit = "stock.warehouse"

    route_service_minutes = fields.Integer(
        string="Service Time per Stop (min)",
        default=30,
        help="How long the vehicle stays at each customer, added to the arrival "
        "times of the next stops.",
    )
